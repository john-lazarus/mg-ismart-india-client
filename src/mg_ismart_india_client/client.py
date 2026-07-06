from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientSession

from .bitcodec import (
    PackedBitReader,
    PackedBitWriter,
    read_fixed_7bit,
    set_fixed_7bit,
    set_msb_bits,
)
from .crypto import (
    MgIndiaApiError,
    decrypt_gateway_body,
    gateway_signature,
    make_device_id,
    normalize_phone,
    tap_signature,
)
from .models import Capabilities, Snapshot, Status, Vehicle
from .tap import (
    decode_control_response,
    decode_pin_response,
    decode_status_response,
    encode_control_request,
    encode_pin_request,
    encode_status_request,
)

TAP_LOGIN_URL = "https://iov-tap.mgindia.co.in/TAP.Web/ota.mp"
TAP_STATUS_URL = "https://iov-tap.mgindia.co.in/TAP.Web/ota.mpv21"
GATEWAY_BASE = "https://iov-gateway.mgindia.co.in/api.app/v1"
USER_AGENT = "CER_IKE_01/2.3.0 (iPad; iOS 26.3; Scale/2.00)"
CONTROL_ATTEMPTS = 15
CONTROL_DELAY = 2.0
LOGIN_ATTEMPTS = 3
LOGIN_DELAY = 1.5
STATUS_ATTEMPTS = 10
STATUS_DELAY = 1.5
LOGIN_DISPATCHER_TEMPLATE_HEX = (
    "11005600882c60c183060c183060c183060c183060c183060c183060c183060c183060c183"
    "060c183060c183060c183060c1ab06200000000020200468acf134468acf1342468acf134"
    "2468acf1342000000000100a0"
)


def _as_list(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "vehicleList", "vehicles", "vinList", "result"):
            if isinstance(data.get(key), list):
                return data[key]
        nested = data.get("data")
        if isinstance(nested, (dict, list)):
            return _as_list(nested)
    return []


def _bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    return None


def _int(v: Any, minv: int | None = None, maxv: int | None = None) -> int | None:
    try:
        i = int(v)
    except Exception:
        return None
    if minv is not None and i < minv:
        return None
    if maxv is not None and i > maxv:
        return None
    return i


def _tenths(v: Any) -> float | None:
    i = _int(v)
    return None if i is None else i / 10


def parse_vehicle(raw: dict[str, Any]) -> Vehicle:
    vin = raw.get("vin") or raw.get("VIN") or raw.get("vinNo") or raw.get("vehicleVin")
    if not vin:
        raise MgIndiaApiError("Vehicle response did not include a VIN")
    name = (
        raw.get("series")
        or raw.get("modelName")
        or raw.get("brandName")
        or str(vin)[-6:]
    )
    return Vehicle(
        str(vin),
        str(name),
        raw.get("brandName"),
        raw.get("modelName") or raw.get("series"),
        str(raw.get("modelYear") or "") or None,
        raw,
    )


def parse_status(raw: dict[str, Any]) -> Status:
    basic = raw.get("basicVehicleStatus", raw)
    locked = _bool(basic.get("lockStatus"))
    driver_door = _bool(basic.get("driverDoor"))
    passenger_door = _bool(basic.get("passengerDoor"))
    rear_left_door = _bool(basic.get("rearLeftDoor"))
    rear_right_door = _bool(basic.get("rearRightDoor"))
    boot = _bool(basic.get("bootStatus"))
    bonnet = _bool(basic.get("bonnetStatus"))
    driver_window = _bool(basic.get("driverWindow"))
    passenger_window = _bool(basic.get("passengerWindow"))
    rear_left_window = _bool(basic.get("rearLeftWindow"))
    rear_right_window = _bool(basic.get("rearRightWindow"))
    # MG India can report a stale driver-window-open bit while the
    # vehicle is otherwise fully closed and locked. Do not raise a false
    # open-window alarm for that known-bad combination.
    if (
        driver_window is True
        and locked is True
        and not any(
            (
                driver_door,
                passenger_door,
                rear_left_door,
                rear_right_door,
                boot,
                bonnet,
                passenger_window,
                rear_left_window,
                rear_right_window,
            )
        )
    ):
        driver_window = False
    return Status(
        status_time=_int(raw.get("statusTime")),
        locked=locked,
        driver_door_open=driver_door,
        passenger_door_open=passenger_door,
        rear_left_door_open=rear_left_door,
        rear_right_door_open=rear_right_door,
        boot_open=boot,
        bonnet_open=bonnet,
        driver_window_open=driver_window,
        passenger_window_open=passenger_window,
        rear_left_window_open=rear_left_window,
        rear_right_window_open=rear_right_window,
        sunroof_open=_bool(basic.get("sunroofStatus")),
        climate_running=(basic.get("remoteClimateStatus") in (2, 3))
        if basic.get("remoteClimateStatus") is not None
        else None,
        interior_temperature=_int(basic.get("interiorTemperature"), -60, 90),
        exterior_temperature=_int(basic.get("exteriorTemperature"), -60, 90),
        fuel_level=_int(basic.get("fuelLevelPrc"), 0, 100),
        range_km=_tenths(basic.get("fuelRange")),
        odometer_km=_tenths(basic.get("mileage")),
        aux_battery_voltage=_tenths(basic.get("batteryVoltage")),
        can_bus_active=_bool(basic.get("canBusActive")),
        last_can_activity=_int(basic.get("timeOfLastCANBUSActivity")),
        handbrake=_bool(basic.get("handBrake")),
        raw=raw,
    )


def discover_capabilities(payloads: list[dict[str, Any]]) -> Capabilities:
    cfg: dict[str, Any] = {}
    feature_ids: set[int] = set()
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for block in (
            payload.get("configuration"),
            payload.get("config"),
            payload.get("modelConfig"),
        ):
            if isinstance(block, dict):
                cfg.update(block)
        for item in _as_list(payload):
            if not isinstance(item, dict):
                continue
            try:
                feature_ids.add(int(item.get("featureId") or item.get("id")))
            except Exception:
                pass

    def enabled(value: Any) -> bool:
        return str(value or "").upper() in {"1", "Y", "YES", "TRUE", "ON", "SUPPORTED"}

    remote = enabled(cfg.get("S61")) or bool(feature_ids)
    mask = str(cfg.get("WINDOW") or "")
    windows = tuple(
        pid
        for flag, pid in zip(mask, (9, 10, 11, 12), strict=False)
        if flag.upper() in {"1", "Y", "T"}
    )
    return Capabilities(
        climate=enabled(cfg.get("T11")) or 2 in feature_ids,
        door_lock=remote,
        find_my_car=remote,
        tailgate=remote and enabled(cfg.get("BOOT")),
        sunroof=remote and enabled(cfg.get("S35")),
        heated_seats=remote and enabled(cfg.get("HeatedSeat")),
        window_param_ids=windows if remote else (),
    )


def encode_login_app(password: str, device_id: str) -> bytes:
    writer = PackedBitWriter()
    writer.write(1, 1)
    writer.write_string(password, 6, 30)
    writer.write_string(device_id, 1, 200)
    return writer.bytes()


def decode_login_response(raw: str) -> tuple[str, str]:
    if len(raw) < 5 or raw[4] != "1":
        raise MgIndiaApiError("Unexpected TAP login response framing")
    payload = bytes.fromhex(raw[5:])
    if len(payload) < 4:
        raise MgIndiaApiError("TAP login response is too short")
    dispatcher_len = payload[2] + (payload[3] << 8)
    dispatcher = payload[:dispatcher_len]
    app = payload[dispatcher_len:]
    uid = read_fixed_7bit(dispatcher, 300, 14).rjust(50, "0")
    reader = PackedBitReader(app)
    reader.read(6)
    token = reader.read_string(40, 40)
    refresh = reader.read_string(40, 40)
    if token != refresh:
        raise MgIndiaApiError("Login token and refresh token differ")
    return uid, token


class MgIndiaClient:
    def __init__(
        self,
        session: ClientSession,
        phone: str,
        password: str,
        vin: str | None = None,
        pin_hash: str | None = None,
    ) -> None:
        self.session = session
        self.phone = normalize_phone(phone)
        self.password = password
        self.vin = vin
        self.pin_hash = pin_hash
        self.device_id = make_device_id(self.phone)
        self.uid: str | None = None
        self.token: str | None = None
        self.vehicle: Vehicle | None = None
        self.capabilities = Capabilities()
        self._event = 1

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash)

    def _next_event(self) -> int:
        self._event = (self._event + 1) & 0x7FFFFFFF
        return self._event

    def _build_login_body(self) -> str:
        dispatcher = bytearray.fromhex(LOGIN_DISPATCHER_TEMPLATE_HEX)
        app = encode_login_app(self.password, self.device_id)
        set_fixed_7bit(dispatcher, 48, self.phone.rjust(50, "0"))
        set_msb_bits(dispatcher, 419, 32, int(time.time()))
        dispatcher[-7:-3] = (len(app) * 2).to_bytes(4, "big")
        dispatcher[-3] = 1
        dispatcher[-2:] = (160).to_bytes(2, "big")
        payload = bytes(dispatcher) + app
        raw_without_length = "1" + payload.hex().upper()
        return f"{len(raw_without_length) + 4:04X}{raw_without_length}"

    async def login(self) -> None:
        last_error: Exception | None = None
        for attempt in range(LOGIN_ATTEMPTS):
            body = self._build_login_body()
            headers = {
                "User-Agent": USER_AGENT,
                "Content-Type": "text/plain",
                "Accept": "*/*",
                "Accept-Language": "en-US;q=1",
                "APP-SIGNATURE": tap_signature(body),
                "SIGNATURE": "1",
            }
            async with self.session.post(
                TAP_LOGIN_URL, data=body, headers=headers, timeout=30
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    last_error = MgIndiaApiError(
                        f"Login failed: HTTP {response.status}"
                    )
                else:
                    try:
                        self.uid, self.token = decode_login_response(text)
                        return
                    except (MgIndiaApiError, ValueError) as err:
                        last_error = err
            if attempt < LOGIN_ATTEMPTS - 1:
                await asyncio.sleep(LOGIN_DELAY)
        raise MgIndiaApiError(
            "Login failed after retrying transient TAP response"
        ) from last_error

    async def gateway_get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.token or not self.uid:
            await self.login()
        clean_path = "/" + path.lstrip("/")
        query = urlencode(params or {})
        signing_path = clean_path + (f"?{query}" if query else "")
        timestamp = str(int(time.time() * 1000))
        content_type = "application/json"
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": content_type,
            "APP-CONTENT-ENCRYPTED": "1",
            "APP-LANGUAGE-TYPE": "en-us",
            "APP-LOGIN-TOKEN": self.token or "",
            "APP-USER-ID": self.uid or "",
            "APP-SEND-DATE": timestamp,
            "APP-VERIFICATION-STRING": gateway_signature(
                signing_path, timestamp, content_type
            ),
            "ORIGINAL-CONTENT-TYPE": content_type,
        }
        async with self.session.get(
            GATEWAY_BASE + clean_path, params=params, headers=headers, timeout=30
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise MgIndiaApiError(
                    f"Gateway {clean_path} failed: HTTP {response.status}"
                )
            headers_out = response.headers
        parsed = json.loads(decrypt_gateway_body(text, headers_out))
        if parsed.get("code") == 7:
            await self.login()
            return await self.gateway_get(path, params)
        if parsed.get("code") not in (0, None):
            raise MgIndiaApiError(
                parsed.get("message") or f"Gateway error code {parsed.get('code')}"
            )
        return parsed

    async def vehicles(self) -> list[Vehicle]:
        data = await self.gateway_get("/vehicle/userVinList")
        vehicles = [parse_vehicle(x) for x in _as_list(data) if isinstance(x, dict)]
        if self.vin:
            self.vehicle = next(
                (v for v in vehicles if v.vin == self.vin),
                vehicles[0] if vehicles else None,
            )
        elif vehicles:
            self.vehicle = vehicles[0]
            self.vin = self.vehicle.vin
        return vehicles

    async def refresh_capabilities(self) -> Capabilities:
        if not self.vin:
            await self.vehicles()
        payloads = []
        for path in (
            "/vehicle/feature/list",
            "/vehicle/service/subscription",
            "/navi/vehicle/co2info",
            "/navi/vehicle/co2info/supplementInfo",
        ):
            try:
                payloads.append(await self.gateway_get(path, {"vin": self.vin}))
            except Exception:
                pass
        self.capabilities = discover_capabilities(payloads)
        return self.capabilities

    async def status(self) -> Status:
        if not self.token:
            await self.login()
        if not self.vin:
            await self.vehicles()
        headers_base = {
            "User-Agent": USER_AGENT,
            "Content-Type": "text/plain",
            "Accept": "*/*",
            "Accept-Language": "en-US;q=1",
            "SIGNATURE": "1",
        }
        for login_attempt in range(2):
            event_id = 0
            for attempt in range(STATUS_ATTEMPTS):
                body = encode_status_request(
                    self.uid or "0" * 50,
                    self.token or "0" * 40,
                    self.vin or "",
                    event_id,
                )
                headers = dict(headers_base)
                headers["APP-SIGNATURE"] = tap_signature(body)
                async with self.session.post(
                    TAP_STATUS_URL, data=body, headers=headers, timeout=30
                ) as response:
                    text = await response.text()
                    if response.status >= 400:
                        raise MgIndiaApiError(f"Status failed: HTTP {response.status}")
                dispatcher, payload = decode_status_response(text)
                result = dispatcher.get("result", 0)
                if result == 2:
                    if login_attempt == 0:
                        await self.login()
                        break
                    raise MgIndiaApiError("TAP status session is invalid")
                if payload:
                    return parse_status(payload)
                if result not in (0, 4, 6):
                    raise MgIndiaApiError(f"Status failed: result {result}")
                event_id = dispatcher.get("eventID", event_id)
                if attempt < STATUS_ATTEMPTS - 1:
                    await asyncio.sleep(STATUS_DELAY)
            else:
                raise MgIndiaApiError("Vehicle status was not ready after polling")
        raise MgIndiaApiError("Status failed after token refresh")

    async def snapshot(self) -> Snapshot:
        if not self.vehicle:
            await self.vehicles()
        caps = await self.refresh_capabilities()
        status = await self.status()
        return Snapshot(
            self.vehicle or Vehicle(self.vin or "unknown", self.vin or "unknown"),
            caps,
            status,
        )

    async def verify_pin(self) -> None:
        if not self.pin_hash:
            raise MgIndiaApiError("Control PIN is not configured")
        for login_attempt in range(2):
            if not self.token or not self.uid:
                await self.login()
            if not self.vin:
                await self.vehicles()
            body = encode_pin_request(
                self.uid or "0" * 50,
                self.token or "0" * 40,
                self.vin or "",
                self._next_event(),
                self.pin_hash,
            )
            async with self.session.post(
                TAP_LOGIN_URL,
                data=body,
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "text/plain",
                    "Accept": "*/*",
                    "Accept-Language": "en-US;q=1",
                    "APP-SIGNATURE": tap_signature(body),
                    "SIGNATURE": "1",
                },
                timeout=30,
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    raise MgIndiaApiError(
                        f"PIN verification failed: HTTP {response.status}"
                    )
            dispatcher = decode_pin_response(text)
            result = dispatcher.get("result", 0)
            if result == 0:
                return
            if result == 2 and login_attempt == 0:
                await self.login()
                continue
            raise MgIndiaApiError(f"PIN verification failed: result {result}")
        raise MgIndiaApiError("PIN verification failed after token refresh")

    async def _control(
        self, name: str, typ: int, params: list[tuple[int, bytes]]
    ) -> None:
        await self.verify_pin()
        event_id = 0
        for attempt in range(CONTROL_ATTEMPTS):
            body = encode_control_request(
                self.uid or "0" * 50,
                self.token or "0" * 40,
                self.vin or "",
                event_id,
                typ,
                params,
            )
            async with self.session.post(
                TAP_STATUS_URL,
                data=body,
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "text/plain",
                    "Accept": "*/*",
                    "Accept-Language": "en-US;q=1",
                    "APP-SIGNATURE": tap_signature(body),
                    "SIGNATURE": "1",
                },
                timeout=30,
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    raise MgIndiaApiError(f"{name} failed: HTTP {response.status}")
            try:
                dispatcher, control = decode_control_response(text)
            except (MgIndiaApiError, ValueError) as err:
                if attempt == 0:
                    await self.login()
                    event_id = 0
                    continue
                raise MgIndiaApiError(f"{name} response could not be decoded") from err
            result = dispatcher.get("result", 0)
            if result in (2, 3) and attempt == 0:
                await self.login()
                event_id = 0
                continue
            if control:
                status = control.get("rvcReqSts")
                if status == b"\x02":
                    return
                if status not in (None, b"\x01"):
                    raise MgIndiaApiError(f"{name} failed: status {status!r}")
            if result not in (0, 4, 6):
                raise MgIndiaApiError(f"{name} failed: result {result}")
            event_id = dispatcher.get("eventID", event_id)
            if attempt < CONTROL_ATTEMPTS - 1:
                await asyncio.sleep(CONTROL_DELAY)
        raise MgIndiaApiError(f"{name} did not complete")

    async def control_climate(self, on: bool) -> None:
        params = (
            [(19, b"\x03"), (20, b"\x03"), (255, b"\x00")]
            if on
            else [(19, b"\x00"), (20, b"\x00"), (255, b"\x00")]
        )
        await self._control("Climate", 6, params)

    async def control_door_lock(self, lock: bool) -> None:
        params = (
            []
            if lock
            else [
                (4, b"\x00"),
                (5, b"\x00"),
                (6, b"\x00"),
                (7, b"\x03"),
                (255, b"\x00"),
            ]
        )
        try:
            await self._control("Door lock", 1 if lock else 2, params)
        except MgIndiaApiError as err:
            # MG India sometimes applies a lock/unlock command but never returns
            # a terminal remote-command status. Treat it as success only when a
            # fresh status read proves the target lock state was achieved.
            if "did not complete" in str(err):
                status = await self.status()
                if status.locked is lock:
                    return
            raise

    async def find_my_car(self) -> None:
        await self._control(
            "Find my car",
            0,
            [(1, b"\x01"), (2, b"\x01"), (3, b"\x01"), (255, b"\x00")],
        )

    async def release_tailgate(self) -> None:
        await self._control(
            "Tailgate",
            2,
            [(4, b"\x00"), (5, b"\x00"), (6, b"\x00"), (7, b"\x02"), (255, b"\x00")],
        )

    async def control_windows(self, open_windows: bool, ids: tuple[int, ...]) -> None:
        selected = set(ids)
        params = [
            (param_id, b"\x01" if param_id in selected else b"\x00")
            for param_id in (8, 9, 10, 11, 12)
        ]
        params.append((13, b"\x03" if open_windows else b"\x00"))
        await self._control("Windows", 3, params)

    async def control_sunroof(self, open_sunroof: bool) -> None:
        await self._control(
            "Sunroof",
            3,
            [
                (8, b"\x01"),
                (9, b"\x00"),
                (10, b"\x00"),
                (11, b"\x00"),
                (12, b"\x00"),
                (13, b"\x03" if open_sunroof else b"\x00"),
            ],
        )

    async def control_heated_seats(self, driver: int, passenger: int) -> None:
        if driver not in range(4) or passenger not in range(4):
            raise MgIndiaApiError("Heated-seat levels must be between 0 and 3")
        await self._control(
            "Heated seats",
            5,
            [(17, bytes([driver])), (18, bytes([passenger])), (255, b"\x00")],
        )
