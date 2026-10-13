"""Offline checks for the approved protocol and identity corrections."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from test_charge_status import CHARGING_70

from mg_ismart_india_client import MgIndiaApiError, MgIndiaClient
from mg_ismart_india_client.bitcodec import PackedBitReader, read_msb_bits
from mg_ismart_india_client.client import (
    MgIndiaCommandIndeterminate,
    decode_login_response,
)
from mg_ismart_india_client.tap import (
    _decode_v21,
    _frame_v21,
    codec21,
    decode_charge_status_response,
    decode_control_response,
    decode_pin_response,
    encode_control_request,
)


def test_actual_optional_lock_and_nonempty_parameter_asn1():
    for params in ([], [(19, b'\x03'), (255, b'\x00')]):
        frame = encode_control_request('U' * 50, 'T' * 40, 'S' * 17, 0, 1, params)
        dispatcher, app = _decode_v21(frame)
        request = codec21().decode('OTARVCReq', app, check_constraints=True)
        assert request['rvcReqType'] == b'\x01'
        assert dispatcher['applicationID'] == '510'
        assert dispatcher['vin'] == 'S' * 17
        if params:
            assert request['rvcParams'] == [
                {'paramId': 19, 'paramValue': b'\x03'},
                {'paramId': 255, 'paramValue': b'\x00'},
            ]
        else:
            assert 'rvcParams' not in request


@pytest.mark.parametrize('raw_soc,expected', [(0, 0.0), (1000, 100.0), (1001, None), (65535, None)])
def test_charge_soc_domain_retains_raw(raw_soc, expected):
    dispatcher, app = _decode_v21(CHARGING_70)
    decoded = codec21().decode('OTARVMVehicleChargingStatusResp', app)
    decoded['vehicleChargingStatus']['powerLevelPrc'] = raw_soc
    encoded = codec21().encode('OTARVMVehicleChargingStatusResp', decoded)
    assert len(encoded) == 63
    frame = _frame_v21(codec21().encode('MPDispatcherBody', dispatcher), encoded)
    charge = decode_charge_status_response(frame)[1]
    assert charge.soc == expected
    assert charge._raw['powerLevelPrc'] == raw_soc


def test_dispatcher_failure_identity_and_frame_boundaries():
    dispatcher, app = _decode_v21(CHARGING_70)
    failed = dict(dispatcher, result=7)
    frame = _frame_v21(codec21().encode('MPDispatcherBody', failed), app)
    actual, charge = decode_charge_status_response(frame)
    assert actual['result'] == 7 and charge is None
    with pytest.raises(ValueError, match='identity'):
        decode_control_response(CHARGING_70)
    for raw in ('', '10000', '1000021', CHARGING_70[:-2]):
        with pytest.raises(ValueError):
            _decode_v21(raw)
    for raw in ('', '11', '11000400'):
        with pytest.raises(ValueError):
            decode_pin_response(raw)
    for raw in ('', '00001', '000011100FFFF'):
        with pytest.raises(MgIndiaApiError):
            decode_login_response(raw)
    for field, value in [('applicationDataEncoding', 'ber'),
                         ('applicationDataProtocolVersion', 514)]:
        changed = dict(dispatcher, **{field: value})
        frame = _frame_v21(codec21().encode('MPDispatcherBody', changed), app)
        with pytest.raises(ValueError, match='unsupported'):
            decode_charge_status_response(frame)


def test_bounded_gateway_recovery_and_configured_vin(monkeypatch):
    class Response:
        status, headers = 200, {}
        async def text(self):
            return json.dumps({'code': 7})
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False

    class Session:
        calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            return Response()

    async def run():
        session = Session()
        client = MgIndiaClient(session, '0000000000', 'synthetic', vin='SYNTHETIC-ABSENT')
        client.uid, client.token = 'U' * 50, 'T' * 40
        client.login = AsyncMock()
        monkeypatch.setattr('mg_ismart_india_client.client.decrypt_gateway_body', lambda text, headers: text)
        with pytest.raises(MgIndiaApiError, match='remains invalid'):
            await client.gateway_get('/synthetic')
        assert session.calls == 2 and client.login.await_count == 1
        client.gateway_get = AsyncMock(return_value={'data': [{'vin': 'SYNTHETIC-FIRST'}]})
        with pytest.raises(MgIndiaApiError, match='absent'):
            await client.vehicles()
        assert client.vehicle is None and client.vin == 'SYNTHETIC-ABSENT'
        client.vin = None
        await client.vehicles()
        assert client.vehicle.vin == client.vin == 'SYNTHETIC-FIRST'
    asyncio.run(run())


@pytest.mark.parametrize('response', ['malformed', 'terminal-2', 'terminal-3', 'terminal-7', 'wrong-vin', 'wrong-type', 'no-cursor'])
def test_ambiguous_command_never_replays(monkeypatch, response):
    async def run():
        client = MgIndiaClient(object(), '0000000000', 'synthetic', vin='S' * 17)
        client.uid, client.token = 'U' * 50, 'T' * 40
        client.verify_pin = AsyncMock()
        client.login = AsyncMock()
        client._post_tap_frame = AsyncMock(return_value='synthetic-response')
        def decode(_text):
            if response == 'malformed':
                raise ValueError('synthetic-malformed')
            return ({'result': int(response[-1]) if response.startswith('terminal-') else 0,
                     'vin': 'X' * 17 if response == 'wrong-vin' else 'S' * 17},
                    {'rvcReqSts': b'\x02' if response != 'no-cursor' else b'\x01',
                     'rvcReqType': b'\x05' if response == 'wrong-type' else b'\x01'})
        monkeypatch.setattr('mg_ismart_india_client.client.decode_control_response', decode)
        with pytest.raises(MgIndiaCommandIndeterminate):
            await client._control('Synthetic lock', 1, [])
        assert client._post_tap_frame.await_count == 1
        assert client.verify_pin.await_count == 1
        assert client.login.await_count == 0
    asyncio.run(run())


def test_bit_read_boundaries_preserve_valid_bits():
    reader = PackedBitReader(b'\xa5')
    assert reader.read(4) == 10
    assert reader.read(4) == 5
    assert reader.read(0) == 0
    with pytest.raises(ValueError):
        reader.read(1)
    assert reader.offset == 8
    with pytest.raises(ValueError):
        reader.read(-1)
    assert read_msb_bits(b'\xa5', 0, 8) == 165
    for offset, count in ((-1, 1), (0, -1), (1, 8), (0, 9)):
        with pytest.raises(ValueError):
            read_msb_bits(b'\xa5', offset, count)


@pytest.mark.parametrize('measured_at,expected', [(100, False), (None, False), (101, True), (103, False)])
def test_lock_timeout_requires_independent_fresh_matching_status(monkeypatch, measured_at, expected):
    async def run():
        client = MgIndiaClient(object(), '0000000000', 'synthetic', vin='S' * 17)
        error = MgIndiaCommandIndeterminate('Door lock did not complete')
        client._control = AsyncMock(side_effect=error)
        client.status = AsyncMock(return_value=type('SyntheticStatus', (), {
            'status_time': measured_at, 'locked': True,
        })())
        clock = iter([100.5, 102.0])
        monkeypatch.setattr('mg_ismart_india_client.client.time.time', lambda: next(clock))
        if expected:
            await client.control_door_lock(True)
        else:
            with pytest.raises(MgIndiaApiError) as caught:
                await client.control_door_lock(True)
            assert caught.value is error
        client._control.assert_awaited_once_with('Door lock', 1, [])
        client.status.assert_awaited_once()
    asyncio.run(run())


def test_lock_verification_failure_preserves_original_error(monkeypatch):
    async def run():
        client = MgIndiaClient(object(), '0000000000', 'synthetic', vin='S' * 17)
        error = MgIndiaCommandIndeterminate('Door lock did not complete')
        client._control = AsyncMock(side_effect=error)
        client.status = AsyncMock(side_effect=MgIndiaApiError('synthetic-read-error'))
        monkeypatch.setattr('mg_ismart_india_client.client.time.time', lambda: 100.5)
        with pytest.raises(MgIndiaApiError) as caught:
            await client.control_door_lock(True)
        assert caught.value is error
        assert caught.value.__suppress_context__
        client._control.assert_awaited_once()
        client.status.assert_awaited_once()
    asyncio.run(run())
