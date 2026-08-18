from mg_ismart_india_client.client import (
    discover_capabilities,
    parse_status,
    parse_vehicle,
)
from mg_ismart_india_client.crypto import (
    gateway_signature,
    hash_control_pin,
    normalize_phone,
    tap_signature,
)
from mg_ismart_india_client.models import Vehicle
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
