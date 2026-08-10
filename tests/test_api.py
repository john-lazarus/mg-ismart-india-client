import random

import pytest

from mg_ismart_india_client.bitcodec import PackedBitWriter
from mg_ismart_india_client.client import (
    decode_login_response,
    discover_capabilities,
    parse_status,
)
from mg_ismart_india_client.crypto import (
    MgIndiaApiError,
    gateway_signature,
    hash_control_pin,
    normalize_phone,
    tap_signature,
)
from mg_ismart_india_client.tap import (
    encode_control_request,
    encode_pin_request,
    encode_status_request,
)


def test_phone_and_pin():
    assert normalize_phone("+91 98765 43210") == "9876543210"
    assert len(hash_control_pin("1234")) == 32


def test_signatures_exist():
    assert len(tap_signature("0123456789ABCDEF")) == 64
    assert len(gateway_signature("/vehicle/userVinList", "1700000000000")) == 64


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


def test_decode_login_response_raises_clean_error_on_rejection():
    # A real MG India rejection response declares a dispatcher_len of only
    # ~6 bytes (vs. the ~86 a successful login carries), which used to
    # crash read_fixed_7bit with IndexError. Reproduce that shape with
    # random bytes rather than a captured server payload.
    rng = random.Random(1234)
    payload = bytearray(rng.randbytes(20))
    payload[2], payload[3] = 6, 0  # dispatcher_len = 6, too short to hold a uid
    raw = "00001" + bytes(payload).hex().upper()

    with pytest.raises(MgIndiaApiError, match="rejected"):
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
