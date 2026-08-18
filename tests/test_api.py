import random

import pytest

from mg_ismart_india_client.bitcodec import PackedBitWriter
from mg_ismart_india_client.client import (
    decode_login_response,
    discover_capabilities,
    encode_login_app,
    parse_status,
    parse_vehicle,
)
from mg_ismart_india_client.crypto import (
    MgIndiaApiError,
    gateway_signature,
    hash_control_pin,
    normalize_phone,
    tap_signature,
)
from mg_ismart_india_client.models import Vehicle
from mg_ismart_india_client.tap import (
    codec11,
    encode_control_request,
    encode_pin_request,
    encode_status_request,
)


def _v11_login_frame(fields: dict) -> str:
    """Build a TAP login response the way decode_login_response reads it:
    a V11 dispatcher body prefixed with the 4-byte framing header."""
    body = codec11().encode("MPDispatcherBodyV11", fields)
    payload = bytes((17, 0, len(body) + 4, 0)) + body
    return "00001" + payload.hex().upper()


def test_phone_and_pin():
    assert normalize_phone("+91 98765 43210") == "9876543210"
    assert len(hash_control_pin("1234")) == 32


def test_signatures_exist():
    assert len(tap_signature("0123456789ABCDEF")) == 64
    assert len(gateway_signature("/vehicle/userVinList", "1700000000000")) == 64


def test_vehicle_parser_color_and_series():
    v = parse_vehicle(
        {
            "vin": "LSJA00000TEST0001",
            "brandName": "MG",
            "modelName": "Comet",
            "series": "EC32",
            "colorName": "Nova Blue",
            "modelYear": "2025",
        }
    )
    assert v.model == "Comet"
    assert v.series == "EC32"
    assert v.color_name == "Nova Blue"


def test_vehicle_legacy_positional_arguments():
    raw = {"vin": "LSJA00000TEST0001"}
    vehicle = Vehicle("vin", "name", "brand", "model", "2025", raw)
    assert (vehicle.raw, vehicle.color_name, vehicle.series) == (raw, None, None)


def test_status_parser():
    s = parse_status(
        {
            "statusTime": 1,
            "basicVehicleStatus": {
                "lockStatus": True,
                "driverDoor": False,
                "fuelLevelPrc": 50,
                "fuelRange": 123,
                "mileage": 456,
                "batteryVoltage": 140,
            },
        }
    )
    assert s.locked is True and s.fuel_level == 50 and s.aux_battery_voltage == 14


def test_tyre_pressure_parser():
    # Raw values from a captured frame; the app showed 33.8 / 35.4 psi for
    # the 169 / 177 readings at the same time.
    s = parse_status(
        {
            "statusTime": 1,
            "basicVehicleStatus": {
                "frontRrightTyrePressure": 179,
                "frontLeftTyrePressure": 169,
                "rearRightTyrePressure": 177,
                "rearLeftTyrePressure": 169,
                "wheelTyreMonitorStatus": 0,
            },
        }
    )
    assert s.front_left_tyre_psi == 33.8
    assert s.front_right_tyre_psi == 35.8
    assert s.rear_left_tyre_psi == 33.8
    assert s.rear_right_tyre_psi == 35.4
    assert s.tyre_monitor_status == 0


def test_tyre_pressure_accepts_corrected_front_right_spelling():
    s = parse_status({"basicVehicleStatus": {"frontRightTyrePressure": 175}})
    assert s.front_right_tyre_psi == 35.0


def test_tyre_pressure_absent_or_zero_is_none():
    s = parse_status({"basicVehicleStatus": {"frontLeftTyrePressure": 0}})
    assert s.front_left_tyre_psi is None
    assert s.front_right_tyre_psi is None
    assert s.tyre_monitor_status is None


def test_decode_login_response_surfaces_server_error_message():
    # A real rejection is a V11 dispatcher with a non-zero result and a
    # human-readable errorMessage. decode_login_response used to crash on it;
    # it must now raise MgIndiaApiError carrying the server's message.
    raw = _v11_login_frame(
        {
            "applicationID": "501",
            "eventCreationTime": 1,
            "messageID": 1,
            "iccID": "12345678901234567890",
            "applicationDataLength": 0,
            "applicationDataProtocolVersion": 513,
            "result": 15030,
            "errorMessage": b"Incorrect password. You may have another 2 attempts",
        }
    )
    with pytest.raises(MgIndiaApiError, match="Incorrect password"):
        decode_login_response(raw)


def test_decode_login_response_raises_clean_error_on_short_dispatcher():
    # A malformed/short response that is not a V11 error dispatcher must still
    # raise a clean MgIndiaApiError instead of crashing with IndexError.
    rng = random.Random(1234)
    payload = bytearray(rng.randbytes(20))
    payload[2], payload[3] = 6, 0  # dispatcher_len = 6, too short to hold a uid
    raw = "00001" + bytes(payload).hex().upper()

    with pytest.raises(MgIndiaApiError):
        decode_login_response(raw)


def test_decode_login_response_round_trip_on_success_shape():
    dispatcher = bytearray(50)
    dispatcher[2], dispatcher[3] = 50, 0  # dispatcher_len = 50, little-endian

    writer = PackedBitWriter()
    writer.write(0, 6)
    writer.write_string("T" * 40, 40, 40)
    writer.write_string("T" * 40, 40, 40)

    payload = bytes(dispatcher) + writer.bytes()
    raw = "00001" + payload.hex().upper()

    uid, token = decode_login_response(raw)
    assert token == "T" * 40
    assert len(uid) == 50


def test_encode_login_app_trims_password_to_app_cap():
    # The MG iSMART India app input field caps the password at 16 chars, so a
    # longer password must encode identically to its first 16 characters.
    long_password = "0123456789ABCDEF" + "extra-that-app-would-never-see"
    assert len(long_password) > 16

    device_id = "device-1"
    assert encode_login_app(long_password, device_id) == encode_login_app(
        long_password[:16], device_id
    )


def test_capabilities_and_encoders():
    c = discover_capabilities(
        [
            {
                "configuration": {
                    "S61": "1",
                    "T11": "1",
                    "WINDOW": "1111",
                    "BOOT": "1",
                    "S35": "1",
                    "HeatedSeat": "1",
                }
            }
        ]
    )
    assert c.climate and c.door_lock and c.window_param_ids == (9, 10, 11, 12)
    assert encode_status_request("1" * 50, "2" * 40, "3" * 17, 7)
    assert encode_control_request("1" * 50, "2" * 40, "3" * 17, 8, 6, [(1, b"\x01")])
    assert encode_pin_request("1" * 50, "2" * 40, "3" * 17, 9, "A" * 32)
