"""Tests for decoding the RvsPosition block carried by every status response.

The shape and magnitudes here mirror real captured MG India frames, which
decode to a plausible Indian street address at a few tens of metres altitude,
with hdop 6-7 and 16 satellites. Coordinates are invented so that a real
owner's parking spot does not end up in the test suite, and speed is non-zero
in the main sample because every captured frame so far is of a parked car.
"""

from mg_ismart_india_client.client import parse_gps_position, parse_status
from mg_ismart_india_client.models import GpsPosition, GpsStatus, Status
from mg_ismart_india_client.tap import codec21

# Values are in the protocol's own units: micro-degrees for the coordinates,
# metres for altitude, tenths of a km/h for speed.
_SAMPLE = {
    "wayPoint": {
        "position": {"latitude": 12971599, "longitude": 77594566, "altitude": 920},
        "heading": 180,
        "speed": 421,
        "hdop": 8,
        "satellites": 11,
    },
    "timestamp4Short": {"seconds": 1755230000},
    "gpsStatus": "fix3D",
}


def test_status_preserves_legacy_raw_positional_argument():
    raw = {"source": "legacy positional caller"}

    status = Status(*([None] * 28), raw)

    assert status.raw is raw
    assert status.gps is None


def test_gps_position_decodes_into_ordinary_units():
    gps = parse_gps_position(_SAMPLE)

    assert gps is not None
    assert gps.latitude == 12.971599
    assert gps.longitude == 77.594566
    assert gps.altitude_m == 920
    assert gps.heading_deg == 180
    assert gps.speed_kmh == 42.1
    assert gps.hdop == 8
    assert gps.satellites == 11
    assert gps.gps_status is GpsStatus.FIX_3D
    assert gps.position_time == 1755230000
    assert gps.has_fix is True


def test_gps_position_survives_a_real_asn1_round_trip():
    # The enum arrives as its identifier string, not a number, so guard the
    # actual codec output rather than a hand-written dict alone.
    codec = codec21()
    decoded = codec.decode("RvsPosition", codec.encode("RvsPosition", _SAMPLE))

    assert decoded["gpsStatus"] == "fix3D"

    gps = parse_gps_position(decoded)
    assert gps is not None
    assert (gps.latitude, gps.longitude) == (12.971599, 77.594566)
    assert gps.gps_status is GpsStatus.FIX_3D


def test_parked_car_shape_seen_in_every_capture_so_far():
    # Real frames all look like this: a 2D fix, speed pinned at 0, 16
    # satellites. Speed must stay a real 0.0 rather than collapsing to None,
    # or a parked car reads as "speed unknown".
    gps = parse_gps_position(
        {
            "wayPoint": {
                "position": {
                    "latitude": 12971599,
                    "longitude": 77594566,
                    "altitude": 35,
                },
                "heading": 41,
                "speed": 0,
                "hdop": 6,
                "satellites": 16,
            },
            "timestamp4Short": {"seconds": 1786728372},
            "gpsStatus": "fix2D",
        }
    )

    assert gps is not None
    assert gps.gps_status is GpsStatus.FIX_2D
    assert gps.has_fix is True
    assert gps.speed_kmh == 0.0
    assert gps.satellites == 16
    assert gps.altitude_m == 35


def test_gps_speed_rejects_negative_boundary_but_preserves_zero():
    negative = parse_gps_position({"wayPoint": {"speed": -1}})
    zero = parse_gps_position({"wayPoint": {"speed": 0}})

    assert negative is not None
    assert negative.speed_kmh is None
    assert zero is not None
    assert zero.speed_kmh == 0.0


def test_gps_position_reports_no_fix_without_dropping_the_block():
    gps = parse_gps_position(
        {
            "wayPoint": {
                "position": {"latitude": 0, "longitude": 0, "altitude": 0},
                "heading": 0,
                "speed": -1000,
                "hdop": 0,
                "satellites": 0,
            },
            "timestamp4Short": {"seconds": 0},
            "gpsStatus": "noGpsSignal",
        }
    )

    assert gps is not None
    assert gps.gps_status is GpsStatus.NO_SIGNAL
    assert gps.has_fix is False
    assert gps.latitude == 0.0 and gps.longitude == 0.0
    # -1000 is the schema floor standing in for "no reading", not -100 km/h.
    assert gps.speed_kmh is None


def test_has_fix_requires_reported_fix_and_both_coordinates():
    assert GpsPosition(12.9, 77.5, gps_status=GpsStatus.FIX_2D).has_fix is True
    assert GpsPosition(None, 77.5, gps_status=GpsStatus.FIX_2D).has_fix is False
    assert GpsPosition(12.9, None, gps_status=GpsStatus.FIX_3D).has_fix is False
    assert GpsPosition(0.0, 0.0, gps_status=GpsStatus.FIX_3D).has_fix is True


def test_gps_position_tolerates_a_missing_or_partial_block():
    assert parse_gps_position(None) is None
    assert parse_gps_position("nonsense") is None

    gps = parse_gps_position({"gpsStatus": "fix2D"})
    assert gps is not None
    assert gps.gps_status is GpsStatus.FIX_2D
    assert gps.has_fix is False
    assert gps.latitude is None
    assert gps.longitude is None
    assert gps.satellites is None


def test_gps_status_also_accepts_a_plain_number():
    assert parse_gps_position({"gpsStatus": 3}).gps_status is GpsStatus.FIX_3D
    assert parse_gps_position({"gpsStatus": 99}).gps_status is None


def test_status_carries_the_gps_position():
    status = parse_status({"statusTime": 1, "gpsPosition": _SAMPLE})

    assert status.gps is not None
    assert (status.gps.latitude, status.gps.longitude) == (12.971599, 77.594566)


def test_status_without_a_gps_block_leaves_gps_none():
    assert parse_status({"statusTime": 1, "basicVehicleStatus": {}}).gps is None
