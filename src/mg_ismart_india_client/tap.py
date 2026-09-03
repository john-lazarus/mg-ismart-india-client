from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

import asn1tools

from .models import ChargeStatus

_LOGGER = logging.getLogger(__name__)

TAP_RESERVED_SIZE = 16
TAP_PROTOCOL_VERSION = 33
V11_PROTOCOL_VERSION = 17
PROTOCOL = 513
STATUS_APP_ID = "511"
CONTROL_APP_ID = "510"
PIN_APP_ID = "313"

ASN_V21 = """MGIndiaTapModule
DEFINITIONS AUTOMATIC TAGS ::= BEGIN
MPDispatcherBody ::= SEQUENCE { uid IA5String(SIZE(50)) OPTIONAL, token IA5String(SIZE(40)) OPTIONAL, applicationID IA5String(SIZE(3)), vin IA5String(SIZE(17)) OPTIONAL, messageID INTEGER(0..255), eventCreationTime INTEGER(0..2147483647), eventID INTEGER(0..2147483647) OPTIONAL, ulMessageCounter INTEGER(0..65535) OPTIONAL, dlMessageCounter INTEGER(0..65535) OPTIONAL, ackMessageCounter INTEGER(0..65535) OPTIONAL, ackRequired BOOLEAN OPTIONAL, applicationDataLength INTEGER(0..65535) OPTIONAL, applicationDataEncoding DataEncodingType OPTIONAL, applicationDataProtocolVersion INTEGER(0..65535) OPTIONAL, testFlag INTEGER(1..3) OPTIONAL, result INTEGER(0..65535) OPTIONAL, errorMessage OCTET STRING(SIZE(1..1024)) OPTIONAL }
DataEncodingType ::= ENUMERATED { perUnaligned(0), der(1), ber(2) }
OTARVMVehicleStatusReq ::= SEQUENCE { vehStatusReqType INTEGER(0..255) }
OTARVCReq ::= SEQUENCE { rvcReqType OCTET STRING(SIZE(1)), rvcParams SEQUENCE SIZE(1..10) OF RvcReqParam OPTIONAL }
RvcReqParam ::= SEQUENCE { paramId INTEGER(0..65535), paramValue OCTET STRING(SIZE(1..255)) }
OTARVMVehicleStatusResp513 ::= SEQUENCE { statusTime INTEGER(0..2147483647), gpsPosition RvsPosition, basicVehicleStatus RvsBasicStatus513, extendedVehicleStatus RvsExtStatus OPTIONAL }
OTARVCStatus513 ::= SEQUENCE { rvcReqType OCTET STRING(SIZE(1)), rvcReqSts OCTET STRING(SIZE(1)), failureType INTEGER(0..255) OPTIONAL, gpsPosition RvsPosition, basicVehicleStatus RvsBasicStatus513 }
RvsPosition ::= SEQUENCE { wayPoint RvsWayPoint, timestamp4Short Timestamp4Short, gpsStatus GPSStatus }
RvsWayPoint ::= SEQUENCE { position RvsWGS84Point, heading INTEGER(0..359), speed INTEGER(-1000..4500), hdop INTEGER(0..1000), satellites INTEGER(0..16) }
RvsWGS84Point ::= SEQUENCE { latitude INTEGER(-90000000..90000000), longitude INTEGER(-180000000..180000000), altitude INTEGER(-100..8900) }
Timestamp4Short ::= SEQUENCE { seconds INTEGER(0..2147483647) }
GPSStatus ::= ENUMERATED { noGpsSignal(0), timeFix(1), fix2D(2), fix3D(3) }
RvsBasicStatus513 ::= SEQUENCE { driverDoor BOOLEAN, passengerDoor BOOLEAN, rearLeftDoor BOOLEAN, rearRightDoor BOOLEAN, bootStatus BOOLEAN, bonnetStatus BOOLEAN, lockStatus BOOLEAN, driverWindow BOOLEAN OPTIONAL, passengerWindow BOOLEAN OPTIONAL, rearLeftWindow BOOLEAN OPTIONAL, rearRightWindow BOOLEAN OPTIONAL, sunroofStatus BOOLEAN OPTIONAL, frontRrightTyrePressure INTEGER(0..255) OPTIONAL, frontLeftTyrePressure INTEGER(0..255) OPTIONAL, rearRightTyrePressure INTEGER(0..255) OPTIONAL, rearLeftTyrePressure INTEGER(0..255) OPTIONAL, wheelTyreMonitorStatus INTEGER(0..255) OPTIONAL, sideLightStatus BOOLEAN, dippedBeamStatus BOOLEAN, mainBeamStatus BOOLEAN, vehicleAlarmStatus INTEGER(0..255) OPTIONAL, engineStatus INTEGER(0..255), powerMode INTEGER(0..255), lastKeySeen INTEGER(0..65535), currentJourneyDistance INTEGER(0..65535), currentJourneyID INTEGER(0..2147483647), interiorTemperature INTEGER(-128..127), exteriorTemperature INTEGER(-128..127), fuelLevelPrc INTEGER(0..255), fuelRange INTEGER(0..65535), remoteClimateStatus INTEGER(0..255), frontLeftSeatHeatLevel INTEGER(0..255) OPTIONAL, frontRightSeatHeatLevel INTEGER(0..255) OPTIONAL, canBusActive BOOLEAN, timeOfLastCANBUSActivity INTEGER(0..2147483647), clstrDspdFuelLvlSgmt INTEGER(0..255), mileage INTEGER(0..2147483647), batteryVoltage INTEGER(0..65535), extendedData1 INTEGER(0..2147483647) OPTIONAL, extendedData2 INTEGER(0..2147483647) OPTIONAL, handBrake BOOLEAN }
RvsExtStatus ::= SEQUENCE { vehicleAlerts SEQUENCE SIZE(0..64) OF VehicleAlertInfo }
VehicleAlertInfo ::= SEQUENCE { id INTEGER(0..255), value INTEGER(0..255) }
OTARVMVehicleChargingStatusResp ::= SEQUENCE { statusTime INTEGER(0..2147483647), gpsPosition RvsPosition, vehicleChargingStatus RvsChargingStatus }
RvsChargingStatus ::= SEQUENCE { realtimePower INTEGER(0..65535), powerLevelPrc INTEGER(0..65535) OPTIONAL, chargingState BOOLEAN, chargingGunState BOOLEAN, fuelRange INTEGER(0..65535), chargingType INTEGER(0..255), chargingTimeLevelPrc INTEGER(0..65535) OPTIONAL, startTime INTEGER(0..2147483647) OPTIONAL, endTime INTEGER(0..2147483647) OPTIONAL, chargingCurrent INTEGER(0..65535), chargingVoltage INTEGER(0..65535), chargingPileID IA5String(SIZE(0..64)) OPTIONAL, chargingPileSupplier IA5String(SIZE(0..64)) OPTIONAL, workingCurrent INTEGER(0..65535) OPTIONAL, workingVoltage INTEGER(0..65535) OPTIONAL, mileageSinceLastCharge INTEGER(0..65535) OPTIONAL, powerUsageSinceLastCharge INTEGER(0..65535) OPTIONAL, mileageOfDay INTEGER(0..65535) OPTIONAL, powerUsageOfDay INTEGER(0..65535) OPTIONAL, staticEnergyConsumption INTEGER(0..65535) OPTIONAL, chargingElectricityPhase INTEGER(0..255) OPTIONAL, chargingDuration INTEGER(0..2147483647) OPTIONAL, lastChargeEndingPower INTEGER(0..65535) OPTIONAL, totalBatteryCapacity INTEGER(0..65535) OPTIONAL, fotaLowestVoltage INTEGER(0..255) OPTIONAL, mileage INTEGER(0..2147483647), extendedData1 INTEGER(0..2147483647) OPTIONAL, extendedData2 INTEGER(0..2147483647) OPTIONAL, extendedData3 IA5String(SIZE(0..1024)) OPTIONAL, extendedData4 IA5String(SIZE(0..1024)) OPTIONAL }
END
"""
ASN_V11 = """MGIndiaTapV11Module
DEFINITIONS AUTOMATIC TAGS ::= BEGIN
MPDispatcherBodyV11 ::= SEQUENCE { uid IA5String(SIZE(50)) OPTIONAL, token IA5String(SIZE(40)) OPTIONAL, applicationID IA5String(SIZE(3)), vin IA5String(SIZE(17)) OPTIONAL, eventCreationTime INTEGER(0..4294967295), eventID INTEGER(0..281474976710655) OPTIONAL, messageID INTEGER(0..255), messageCounter MessageCounter OPTIONAL, ackRequired BOOLEAN OPTIONAL, statelessDispatcherMessage BOOLEAN OPTIONAL, crqmRequest BOOLEAN OPTIONAL, basicPosition BasicPosition OPTIONAL, networkInfo NetworkInfo OPTIONAL, simInfo NumericString(SIZE(19)) OPTIONAL, hmiLanguage LanguageType OPTIONAL, iccID NumericString(SIZE(20)), applicationDataLength INTEGER(0..4294967295), applicationDataEncoding DataEncodingType OPTIONAL, applicationDataProtocolVersion INTEGER(0..65535), testFlag INTEGER(1..3) OPTIONAL, result INTEGER(0..65535) OPTIONAL, errorMessage OCTET STRING(SIZE(1..1024)) OPTIONAL }
MessageCounter ::= SEQUENCE { uplinkCounter INTEGER(0..255), downlinkCounter INTEGER(0..255) }
BasicPosition ::= SEQUENCE { latitude INTEGER(-90000000..90000000), longitude INTEGER(-180000000..180000000) }
NetworkInfo ::= SEQUENCE { mccNetwork NumericString(SIZE(3)), mncNetwork NumericString(SIZE(3)), mccSim NumericString(SIZE(3)), mncSim NumericString(SIZE(3)), signalStrength INTEGER(0..99) }
LanguageType ::= ENUMERATED { simplifiedChinese(0), english(1), spanish(2), arabic(3), hindi(4) }
DataEncodingType ::= ENUMERATED { perUnaligned(0), der(1), ber(2) }
PINVerificationReq ::= SEQUENCE { pin IA5String(SIZE(32)) }
END
"""


@lru_cache(maxsize=1)
def codec21():
    return asn1tools.compile_string(ASN_V21, "uper")


@lru_cache(maxsize=1)
def codec11():
    return asn1tools.compile_string(ASN_V11, "uper")


def _frame_v21(dispatcher: bytes, app: bytes) -> str:
    dispatcher_length = len(dispatcher) + 3
    if dispatcher_length > 255:
        raise ValueError("TAP dispatcher too large")
    payload = (
        bytes((TAP_PROTOCOL_VERSION, dispatcher_length, 0))
        + bytes(TAP_RESERVED_SIZE)
        + dispatcher
        + app
    )
    return "1" + f"{len(payload) + 3:04X}" + payload.hex().upper()


def _dispatcher(
    uid: str,
    token: str,
    vin: str,
    app_id: str,
    app: bytes,
    event_id: int,
    msg_id: int = 1,
) -> bytes:
    return codec21().encode(
        "MPDispatcherBody",
        {
            "uid": uid,
            "token": token,
            "applicationID": app_id,
            "vin": vin,
            "messageID": msg_id,
            "eventCreationTime": int(time.time()),
            "eventID": event_id,
            "ulMessageCounter": 0,
            "dlMessageCounter": 0,
            "ackMessageCounter": 0,
            "ackRequired": False,
            "applicationDataLength": len(app),
            "applicationDataEncoding": "perUnaligned",
            "applicationDataProtocolVersion": PROTOCOL,
            "testFlag": 2,
            "result": 0,
        },
    )


def encode_status_request(uid: str, token: str, vin: str, event_id: int) -> str:
    app = codec21().encode("OTARVMVehicleStatusReq", {"vehStatusReqType": 2})
    return _frame_v21(_dispatcher(uid, token, vin, STATUS_APP_ID, app, event_id), app)


# The 63-byte EV charging frame answers a DIFFERENT request than the 195-byte full
# status: messageID 8 with an empty application payload (applicationDataLength 0),
# not the messageID 1 / OTARVMVehicleStatusReq status request. This was read off
# captured app traffic (mid=8 -> 63-byte charge frame; mid=1 -> 195-byte status;
# neither request ever returned the other frame) and confirmed live. The status
# request never elicits the charging frame, so charging must be polled with this.
CHARGE_STATUS_MESSAGE_ID = 8


def encode_charge_status_request(
    uid: str, token: str, vin: str, event_id: int
) -> str:
    return _frame_v21(
        _dispatcher(
            uid,
            token,
            vin,
            STATUS_APP_ID,
            b"",
            event_id,
            msg_id=CHARGE_STATUS_MESSAGE_ID,
        ),
        b"",
    )


def encode_control_request(
    uid: str,
    token: str,
    vin: str,
    event_id: int,
    typ: int,
    params: list[tuple[int, bytes]],
) -> str:
    app = codec21().encode(
        "OTARVCReq",
        {
            "rvcReqType": bytes([typ]),
            "rvcParams": [{"paramId": i, "paramValue": v} for i, v in params],
        },
    )
    return _frame_v21(_dispatcher(uid, token, vin, CONTROL_APP_ID, app, event_id), app)


def encode_pin_request(
    uid: str, token: str, vin: str, event_id: int, pin_hash: str
) -> str:
    app = codec11().encode("PINVerificationReq", {"pin": pin_hash})
    body = codec11().encode(
        "MPDispatcherBodyV11",
        {
            "uid": uid,
            "token": token,
            "applicationID": PIN_APP_ID,
            "vin": vin,
            "eventCreationTime": int(time.time()),
            "messageID": 1,
            "messageCounter": {"uplinkCounter": 1, "downlinkCounter": 0},
            "simInfo": "1234567890987654321",
            "iccID": "12345678901234567890",
            "applicationDataLength": len(app),
            "applicationDataEncoding": "perUnaligned",
            "applicationDataProtocolVersion": PROTOCOL,
            "testFlag": 2,
        },
    )
    dispatcher_length = len(body) + 4
    if dispatcher_length > 255:
        raise ValueError("TAP PIN dispatcher too large")
    payload = bytes((V11_PROTOCOL_VERSION, 0, dispatcher_length, 0)) + body + app
    return f"{len(payload) * 2 + 5:04X}1" + payload.hex().upper()


def _decode_v21(raw: str) -> tuple[dict[str, Any], bytes | None]:
    if len(raw) < 5 or raw[0] != "1":
        raise ValueError("unexpected TAP v2.1 response framing")
    data = bytes.fromhex(raw[5:])
    if len(data) < 19:
        raise ValueError("short TAP v2.1 response")
    dispatcher_length = data[1]
    dispatcher_end = TAP_RESERVED_SIZE + dispatcher_length
    if dispatcher_length < 3 or dispatcher_end > len(data):
        raise ValueError("invalid TAP dispatcher length")
    dispatcher = codec21().decode("MPDispatcherBody", data[19:dispatcher_end])
    app_length = dispatcher.get("applicationDataLength", 0) or 0
    if not app_length:
        return dispatcher, None
    app = data[dispatcher_end : dispatcher_end + app_length]
    if len(app) != app_length:
        raise ValueError("truncated TAP app data")
    return dispatcher, app


def decode_status_response(raw: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    disp, app = _decode_v21(raw)
    return disp, codec21().decode("OTARVMVehicleStatusResp513", app) if app else None


def decode_control_response(raw: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    disp, app = _decode_v21(raw)
    return disp, codec21().decode("OTARVCStatus513", app) if app else None


def decode_pin_response(raw: str) -> dict[str, Any]:
    payload = bytes.fromhex(raw[5:] if len(raw) >= 5 and raw[4] == "1" else raw)
    dispatcher_length = payload[2]
    return codec11().decode("MPDispatcherBodyV11", payload[4:dispatcher_length])


# EV charging status: a 63-byte app-id 511 frame, distinct from the 195-byte full
# status (OTARVMVehicleStatusResp513). It decodes as OTARVMVehicleChargingStatusResp
# (statusTime, gpsPosition, then the RvsChargingStatus charging block). org.bn encodes
# that SET in canonical tag order with the OPTIONAL-presence bitmap in the preamble,
# which the tag-ordered SEQUENCE above reproduces exactly (verified by byte-exact
# re-encode of captured frames).
CHARGE_STATUS_APP_LEN = 63

# Charging-field scales: SOC and range in tenths, voltage in quarter-volts, current in
# 0.05 A steps about a 1000 A zero point (so it reads ~0 A when idle, positive while
# charging).
_SOC_FACTOR = 0.1
_RANGE_FACTOR = 0.1
_VOLTAGE_FACTOR = 0.25
_CURRENT_FACTOR = 0.05
_CURRENT_ZERO_A = 1000.0
# Same odometer scale the status frame uses for its own `mileage` field
# (see parse_status, which reports odometer_km as mileage / 10).
_MILEAGE_FACTOR = 0.1
# Pack energy (realtimePower / lastChargeEndingPower / totalBatteryCapacity) is
# reported in tenths of a kWh: energy / SOC holds at ~37 kWh usable across every
# captured frame from 45% to 100% SOC, and the scale matches the global SAIC
# schema for these same fields.
_ENERGY_FACTOR = 0.1
# workingVoltage is the pack voltage at 2.5 V resolution (= chargingVoltage / 10
# in every captured frame).
_WORKING_VOLTAGE_FACTOR = 2.5
# chargingTimeLevelPrc sends this when no target/countdown applies (idle, full).
_TIME_LEVEL_NA = 0xFFFF


def _amps(raw: int | None) -> float | None:
    """Charge/working current in amperes, or ``None``.

    Reads ~0 A at the idle draw, so callers gate on
    :attr:`~mg_ismart_india_client.models.ChargeStatus.is_charging` rather than on
    a zero current.
    """
    if raw is None:
        return None
    return _CURRENT_ZERO_A - raw * _CURRENT_FACTOR


def _scaled(raw: int | None, factor: float) -> float | None:
    """Rescale an OPTIONAL integer field into its unit, passing ``None`` through."""
    return None if raw is None else raw * factor


def _decode_charge_app(app: bytes | None) -> ChargeStatus | None:
    """Decode the application payload of a charging frame, or ``None`` if it
    isn't one.

    Every field the frame carries is mapped onto a documented
    :class:`~mg_ismart_india_client.models.ChargeStatus` attribute. Values are what
    the vehicle actually sent: nothing is derived from other fields, and nothing is
    rounded, so presentation precision stays the caller's decision. Fields with a
    confirmed scale are rescaled into their declared unit; the rest keep the
    vehicle's integer and are named with a ``_raw`` suffix rather than being dressed
    up in a unit the decoder cannot back up. Current reads ~0 A when idle (small
    housekeeping draw), so callers should still gate current on
    :attr:`~mg_ismart_india_client.models.ChargeStatus.is_charging`.
    """
    if not app or len(app) != CHARGE_STATUS_APP_LEN:
        return None
    try:
        frame = codec21().decode("OTARVMVehicleChargingStatusResp", app)
        cs = frame["vehicleChargingStatus"]
        soc = cs.get("powerLevelPrc")
        time_level = cs.get("chargingTimeLevelPrc")
        return ChargeStatus(
            is_charging=cs["chargingState"],
            is_plugged_in=cs["chargingGunState"],
            charging_type=cs["chargingType"],
            charging_electricity_phase=cs.get("chargingElectricityPhase"),
            soc=_scaled(soc, _SOC_FACTOR),
            range_km=cs["fuelRange"] * _RANGE_FACTOR,
            charging_voltage=cs["chargingVoltage"] * _VOLTAGE_FACTOR,
            charging_current=_amps(cs["chargingCurrent"]),
            battery_energy_kwh=cs["realtimePower"] * _ENERGY_FACTOR,
            working_voltage=_scaled(cs.get("workingVoltage"), _WORKING_VOLTAGE_FACTOR),
            working_current=_amps(cs.get("workingCurrent")),
            charge_time_elapsed_s=cs.get("chargingDuration"),
            start_time=cs.get("startTime") or None,
            end_time=cs.get("endTime") or None,
            charge_time_remaining_min=(
                None if time_level == _TIME_LEVEL_NA else time_level
            ),
            charging_pile_id=cs.get("chargingPileID") or None,
            charging_pile_supplier=cs.get("chargingPileSupplier") or None,
            odometer_km=cs["mileage"] * _MILEAGE_FACTOR,
            distance_since_last_charge_km=_scaled(
                cs.get("mileageSinceLastCharge"), _MILEAGE_FACTOR
            ),
            power_usage_since_last_charge_kwh=_scaled(
                cs.get("powerUsageSinceLastCharge"), _ENERGY_FACTOR
            ),
            mileage_of_day_raw=cs.get("mileageOfDay"),
            power_usage_of_day_raw=cs.get("powerUsageOfDay"),
            static_energy_consumption_raw=cs.get("staticEnergyConsumption"),
            total_battery_capacity_kwh=_scaled(
                cs.get("totalBatteryCapacity"), _ENERGY_FACTOR
            ),
            last_charge_ending_power_kwh=_scaled(
                cs.get("lastChargeEndingPower"), _ENERGY_FACTOR
            ),
            fota_lowest_voltage_raw=cs.get("fotaLowestVoltage"),
            status_time=frame["statusTime"],
            extended_data_1=cs.get("extendedData1"),
            extended_data_2=cs.get("extendedData2"),
            extended_data_3=cs.get("extendedData3") or None,
            extended_data_4=cs.get("extendedData4") or None,
            _raw=cs,
        )
    except (KeyError, ValueError, TypeError, IndexError, asn1tools.Error):
        # Not the charging frame: wrong ASN.1 type, a payload that fails to decode
        # against this schema (asn1tools.Error), or a missing mandatory field.
        return None


def decode_charge_status_response(
    raw: str,
) -> tuple[dict[str, Any], ChargeStatus | None]:
    """Decode a TAP v2.1 frame into its dispatcher and charging status, if present.

    Mirrors :func:`decode_status_response` / :func:`decode_control_response`: the
    dispatcher is always returned (pollers need its result code and event cursor)
    and the second element is the decoded charging frame, or ``None`` when the
    response carries a different frame shape.

    :raises ValueError: if the framing is malformed, so a poller that can no longer
        read the dispatcher fails loudly instead of polling blind.
    """
    dispatcher, app = _decode_v21(raw)
    return dispatcher, _decode_charge_app(app)


def decode_status_and_charge(
    raw: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, ChargeStatus | None]:
    """Decode one TAP frame into its dispatcher, full status, and charging status.

    The 195-byte full-status frame (``OTARVMVehicleStatusResp513``) and the
    63-byte charging frame answer different requests (the status request vs. the
    :func:`encode_charge_status_request` charge request), so any one response holds
    at most one of them. This decodes whichever shape a given response carries
    without raising on the other -- a single tolerant decoder both request pollers
    can share: the status dict is ``None`` unless the frame is the full status, the
    :class:`~mg_ismart_india_client.models.ChargeStatus` is ``None`` unless it is
    the charging frame, and both are ``None`` for an empty/ack frame. The
    dispatcher is always returned so the poller keeps its result code and event
    cursor.

    :raises ValueError: if the framing is malformed (same contract as the
        single-shape decoders), so a poller that can no longer read the dispatcher
        fails loudly instead of polling blind.
    """
    dispatcher, app = _decode_v21(raw)
    if not app:
        return dispatcher, None, None
    charge = _decode_charge_app(app)
    if charge is not None:
        return dispatcher, None, charge
    try:
        status = codec21().decode("OTARVMVehicleStatusResp513", app)
    except (ValueError, TypeError, KeyError, IndexError, asn1tools.Error) as exc:
        # Not the full-status shape either (e.g. a control result): report neither
        # frame rather than raising, so the poll loop keeps going. Logged because
        # this is also where a schema regression would land, and silently it looks
        # identical to an ordinary non-status frame -- the poll then spends its
        # whole budget and fails with "not ready after polling" and no cause.
        _LOGGER.debug("Frame is not the full-status shape: %s", exc)
        status = None
    return dispatcher, status, charge


def decode_charge_status(raw: str) -> ChargeStatus | None:
    """Decode the 63-byte EV-charging status frame (app-id 511).

    Tolerant wrapper around :func:`decode_charge_status_response` for callers that
    only want the charging data: returns ``None`` when the frame is not the 63-byte
    charging shape (e.g. it's the 195-byte full status, an empty ack, or malformed).
    This is the only place ``None`` means "not a charging frame";
    :meth:`~mg_ismart_india_client.client.MgIndiaClient.charge_status` raises
    instead of passing it on.
    """
    try:
        return decode_charge_status_response(raw)[1]
    except (ValueError, IndexError):
        return None
