"""Tests for the EV-charging status decoder and its polling loop.

Decoder fixtures are captured MG Windsor EV responses across a charge session
(SOC 45% -> 100%) at several charge currents. They are SANITIZED: the account id,
session token, VIN, GPS coordinates and framing identifiers have been replaced
with synthetic values, while the charging payload (the bytes under test) is
untouched -- so each decoded value below still matches what the phone app showed
on screen at capture time. The frame decodes as the ASN.1 type
OTARVMVehicleChargingStatusResp recovered from the app.
"""

from __future__ import annotations

import asyncio

import asn1tools
import pytest

from mg_ismart_india_client import (
    ChargingStatusUnavailable,
    MgIndiaApiError,
    MgIndiaClient,
)
from mg_ismart_india_client.tap import (
    _decode_v21,
    codec21,
    decode_charge_status,
)

# SOC 70%, 223 km, 382 V, ~5 A, actively charging
CHARGING_70 = (
    "100C721750000000000000000000000000000000000F0F983060C183060C183060C183"
    "060C183060C183060C183060C183060C183060C183060C183060C183060C183060C183"
    "060C18305AC183060B5A3060C16B860C182D60C183060C183060C1830C38B1E46AC58D"
    "48B4EA56933983060C183060C183109000000000000000000FC0201400000D4FEA4B6A"
    "BA9500ABA95000190043E801E000000002F3C30004100AF308B6020114D4FDE781AAEB"
    "CE11373017E13730026415A401600002F4D008200038FE5"
)

# SOC 74%, 233 km, still charging
CHARGING_74 = (
    "100C721750000000000000000000000000000000000F0F983060C183060C183060C183"
    "060C183060C183060C183060C183060C183060C183060C183060C183060C183060C183"
    "060C18305AC183060B5A3060C16B860C182D60C183060C183060C1830C38B1E46AC58D"
    "48B4EA56933983060C183060C183109000000000000000000FC0201400000D4FEBAF0A"
    "BA9500ABA95000192303E801A000000002F3C30004440B93091A0200F7D4FDE781AAEB"
    "CE11373817E53738026415A4012C00034DB808880038FE5"
)

# SOC 100%, 320 km, idle: plugged in but not charging (full); current fell to 0
IDLE_100 = (
    "100C721750000000000000000000000000000000000F0F983060C183060C183060C183"
    "060C183060C183060C183060C183060C183060C183060C183060C183060C183060C183"
    "060C18305AC183060B5A3060C16B860C182D60C183060C183060C1830C38B1E46AC58D"
    "48B4EA56933983060C183060C183109000000000000000000FC0201400000D4FFAA0AA"
    "BA9500ABA95000191D63E8025600000002F3C30005D40FA10C8006FFFF000000000000"
    "0001388018B93880027800000000000000000BA80038FE5"
)

# SOC 45%, ~17 A charging: a low-SOC, high-current point. Pins the energy scale
# far from full (16.6 kWh / 0.45 = 36.9 kWh usable, same pack size the near-full
# frames imply) and the current scale near the top of the observed 4-18 A sweep.
CHARGING_17A_SOC45 = (
    "100C721750000000000000000000000000000000000F0F983060C183060C183060C183"
    "060C183060C183060C183060C183060C183060C183060C183060C183060C183060C183"
    "060C18305AC183060B5A3060C16B860C182D60C183060C183060C1830C38B1E46AC58D"
    "48B4EA56933983060C183060C183109000000000000000000FC0201400000D508C250A"
    "BA9500ABA95000191CA3E801E000000002F3C3000298070B058C0201ACD508C125AB01"
    "8159332817A13328025C0E800218000004B005300039634"
)

# SOC 80%, ~11 A charging: a second, higher amperage point that pins the current
# scale (idle=0 A + 5 A alone can't distinguish scale from offset).
CHARGING_11A = (
    "100C721750000000000000000000000000000000000F0F983060C183060C183060C183"
    "060C183060C183060C183060C183060C183060C183060C183060C183060C183060C183"
    "060C18305AC183060B5A3060C16B860C182D60C183060C183060C1830C38B1E46AC58D"
    "48B4EA56933983060C183060C183109000000000000000000FC0201400000D5010A08A"
    "BA9500ABA950001926E3E801A000000002F3C30004A80C8309F60200B7D501081DAAF2"
    "0F49352017E5352002640ABC012C000007B009500039294"
)


def test_charging_70():
    s = decode_charge_status(CHARGING_70)
    assert s is not None
    assert s.is_charging is True
    assert s.is_plugged_in is True
    assert s.charging_type == 2
    assert s.soc == 70.0
    assert s.range_km == 223.0
    assert s.charging_voltage == 382.0
    assert s.charging_current == pytest.approx(4.2)
    assert s.charge_time_elapsed_s == 24218
    assert s.start_time == 1786704832
    assert s.status_time == 1786729051
    # pack energy: SOC 70% x 37.3 kWh usable ~= 26.0 kWh (realtimePower x 0.1)
    assert s.battery_energy_kwh == pytest.approx(26.0)
    assert s.last_charge_energy_kwh == pytest.approx(26.0)
    # working V/I mirror the charging pair (coarser voltage, same current)
    assert s.working_voltage == 382.5
    assert s.working_current == pytest.approx(4.2)
    # fields the app does not render but the frame still carries
    assert s.odometer_km == pytest.approx(23344.5)
    assert s.distance_since_last_charge_km == pytest.approx(138.5)


def test_charging_74():
    s = decode_charge_status(CHARGING_74)
    assert s is not None
    assert s.is_charging is True
    assert s.soc == 74.0
    assert s.range_km == 233.0
    # exact quarter-volt step: the decoder must not round this to 382.2
    assert s.charging_voltage == 382.25
    assert s.charging_current == pytest.approx(4.1)
    assert s.battery_energy_kwh == pytest.approx(27.3)
    # same charge session as CHARGING_70: session start and odometer unchanged
    assert s.start_time == 1786704832
    assert s.odometer_km == pytest.approx(23344.5)
    assert s.distance_since_last_charge_km == pytest.approx(138.5)


def test_charging_11a():
    # second amperage point: raw current maps to ~10.8 A, so the (zero, scale)
    # pair holds across 0 A / ~4 A / ~11 A rather than only fitting the 5 A frame
    s = decode_charge_status(CHARGING_11A)
    assert s is not None
    assert s.is_charging is True
    assert s.soc == 80.0
    assert s.charging_current == pytest.approx(10.8)
    assert s.working_current == pytest.approx(10.8)
    assert s.battery_energy_kwh == pytest.approx(29.8)


def test_charging_17a_soc45():
    # low SOC, high current: energy (16.6 kWh) still implies ~37 kWh usable, so the
    # kWh scale is not an artifact of the near-full frames
    s = decode_charge_status(CHARGING_17A_SOC45)
    assert s is not None
    assert s.is_charging is True
    assert s.soc == 45.0
    assert s.charging_current == pytest.approx(17.1)
    assert s.battery_energy_kwh == pytest.approx(16.6)
    assert s.battery_energy_kwh / (s.soc / 100) == pytest.approx(37.0, abs=0.5)


def test_idle_100():
    s = decode_charge_status(IDLE_100)
    assert s is not None
    # plugged in but not charging (here: full)
    assert s.is_charging is False
    assert s.is_plugged_in is True
    assert s.soc == 100.0
    assert s.range_km == 320.0
    assert s.charging_voltage == 395.5
    assert s.charging_current == 0.0
    assert s.working_current == 0.0
    # full pack: 37.3 kWh usable
    assert s.battery_energy_kwh == pytest.approx(37.3)
    # no active session, and the time-to-target sentinel decodes to None
    assert s.start_time is None
    assert s.end_time is None
    assert s.charging_time_level_prc_raw is None
    assert s.distance_since_last_charge_km == 0.0


def test_non_charging_frame_returns_none():
    # malformed / non-charging input must not raise, just yield None
    assert decode_charge_status("") is None
    assert decode_charge_status("garbage") is None


@pytest.mark.parametrize(
    "frame", [CHARGING_70, CHARGING_74, CHARGING_11A, CHARGING_17A_SOC45, IDLE_100]
)
def test_charging_frame_reencodes_byte_for_byte(frame):
    # the ASN.1 transcription is exact, not just plausible: decoding the app
    # payload and re-encoding it must reproduce the original bytes. This is the
    # guarantee that lets us trust fields the app never renders.
    _, app = _decode_v21(frame)
    codec = codec21()
    decoded = codec.decode("OTARVMVehicleChargingStatusResp", app)
    assert codec.encode("OTARVMVehicleChargingStatusResp", decoded) == app


def test_wrong_length_app_that_fails_asn_decode_returns_none():
    # a 63-byte payload that is the right size but not a charging frame makes
    # asn1tools raise its own error class (not a ValueError); the tolerant
    # decoder must swallow that and report "not a charging frame", not crash.
    from mg_ismart_india_client.tap import CHARGE_STATUS_APP_LEN, _decode_charge_app

    with pytest.raises(asn1tools.Error):
        codec21().decode(
            "OTARVMVehicleChargingStatusResp", b"\xff" * CHARGE_STATUS_APP_LEN
        )
    assert _decode_charge_app(b"\xff" * CHARGE_STATUS_APP_LEN) is None


# --- charge_status() polling loop -------------------------------------------
#
# These drive the loop through _post_status_frame and decode_charge_status_response
# rather than over HTTP, so each test scripts exactly the frames the vehicle
# returns and asserts on how the poll reacts.

CHARGE_SENTINEL = object()


def _client():
    client = MgIndiaClient(
        object(),
        "9876543210",
        "secret",
        vin="VIN12345678901234",
        pin_hash="A" * 32,
    )
    client.uid = "uid"
    client.token = "token"
    return client


def _run_charge_status(monkeypatch, responses, *, attempts=3):
    """Run charge_status() against a scripted list of (dispatcher, charge) frames.

    Returns (result, event_ids, logins) where event_ids are the poll cursors the
    loop sent and logins counts the re-login calls it made.
    """
    from mg_ismart_india_client import client as client_mod

    client = _client()
    event_ids: list[int] = []
    logins: list[str] = []
    queued = list(responses)

    async def post(event_id, _label):
        event_ids.append(event_id)
        return "frame"

    async def login():
        logins.append("login")

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(client_mod, "STATUS_ATTEMPTS", attempts)
    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(client, "_post_status_frame", post)
    monkeypatch.setattr(client, "login", login)
    monkeypatch.setattr(
        client_mod,
        "decode_charge_status_response",
        lambda _text: queued.pop(0),
    )

    result = asyncio.run(client.charge_status())
    return result, event_ids, logins


def test_charge_status_returns_first_charging_frame(monkeypatch):
    result, event_ids, logins = _run_charge_status(
        monkeypatch,
        [
            ({"result": 4, "eventID": 111}, None),
            ({"result": 0}, CHARGE_SENTINEL),
        ],
    )

    assert result is CHARGE_SENTINEL
    # the poll cursor from the first response is carried into the second request
    assert event_ids == [0, 111]
    assert logins == []


def test_charge_status_raises_when_budget_runs_out(monkeypatch):
    # an idle vehicle sends a charging frame of its own (see test_idle_100), so a
    # budget that expires without any frame means the data was unavailable, not
    # that the vehicle is idle. It must not come back as a None the caller could
    # read as a known state.
    with pytest.raises(
        ChargingStatusUnavailable, match="not available after polling"
    ):
        _run_charge_status(
            monkeypatch,
            [({"result": 4, "eventID": index}, None) for index in range(1, 4)],
        )


def test_charge_status_returns_idle_frame_as_a_value(monkeypatch):
    # plugged-in-but-idle is a frame, not an absence: it comes back as an
    # ordinary ChargeStatus rather than through the unavailable path
    result, _event_ids, logins = _run_charge_status(
        monkeypatch,
        [({"result": 0}, decode_charge_status(IDLE_100))],
    )

    assert result is not None
    assert result.is_charging is False
    assert result.is_plugged_in is True
    assert logins == []


def test_charge_status_relogs_in_once_on_invalid_session(monkeypatch):
    result, event_ids, logins = _run_charge_status(
        monkeypatch,
        [
            ({"result": 2}, None),
            ({"result": 0}, CHARGE_SENTINEL),
        ],
    )

    assert result is CHARGE_SENTINEL
    assert logins == ["login"]
    # the retry restarts the poll from a fresh cursor
    assert event_ids == [0, 0]


def test_charge_status_raises_when_session_stays_invalid(monkeypatch):
    with pytest.raises(MgIndiaApiError, match="session is invalid"):
        _run_charge_status(
            monkeypatch,
            [({"result": 2}, None), ({"result": 2}, None)],
        )


def test_charge_status_raises_on_unexpected_result(monkeypatch):
    # an unknown result code must surface rather than being reported as "not charging"
    with pytest.raises(MgIndiaApiError, match="result 9"):
        _run_charge_status(monkeypatch, [({"result": 9}, None)])
