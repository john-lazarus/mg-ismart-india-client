# MG iSMART India Client

Python client for the MG iSMART India TAP/gateway API.

This package contains the protocol/client layer used by the MG iSMART India Home Assistant work. It is intentionally separate from Home Assistant so it can be tested and released independently.

## Stability

The package follows semantic versioning from 1.0.0: breaking changes come only in a new major version.

## Install

```bash
pip install mg-ismart-india-client
```

## Basic use

```python
import aiohttp
from mg_ismart_india_client import MgIndiaClient, hash_control_pin

async with aiohttp.ClientSession() as session:
    client = MgIndiaClient(
        session,
        phone="9876543210",
        password="your-password",
        vin="YOURVINHERE",
        pin_hash=hash_control_pin("1234"),
    )

    await client.login()
    vehicles = await client.vehicles()
    status = await client.status()

    # On an EV, ask the same poll for the charging frame too: it lands on
    # status.charge (None when none arrived -- routine, not an error), and
    # saves the second round trip a separate charge_status() would cost.
    #
    # Only set this where a charging frame is expected. The loop waits for one,
    # so a vehicle that never sends it spends the full poll budget on every call.
    status = await client.status(include_charge=True)
    print(status.charge)
```

Control methods require a configured PIN hash. The raw 4-digit control PIN is not stored by the client.

## Several cars on one account

MG India allows one session per account, so use one client per account. Run each car's calls inside `for_vehicle()`. It takes a lock on the client, binds that car's VIN, PIN hash and cached vehicle and capabilities, and saves them back when the block ends:

```python
client = MgIndiaClient(session, phone="9876543210", password="your-password")

async with client.for_vehicle("FIRSTVIN", hash_control_pin("1234")) as car:
    first = await car.status()

async with client.for_vehicle("SECONDVIN") as car:
    second = await car.status()
```

Calls made outside `for_vehicle()` work as before for a single car set in the constructor. Do not mix the two styles: `for_vehicle()` leaves the last car it used bound to the client.

## Waiting for a sleeping car

`status()` polls until the car answers, for up to 30 x 1.5 s (45 s) for the status request. A parked car can take longer to wake than one that is awake. Pass `status_timeout` (seconds) to change the status wait:

```python
client = MgIndiaClient(session, phone="9876543210", password="your-password", status_timeout=90)
```

It still returns as soon as the car answers. The charging frame (`status(include_charge=True)`, `charge_status()`) keeps its own 15 s wait, which `status_timeout` does not change.

## Is the car moving?

`Status.is_moving` is True only when the GPS has a usable fix and reports a speed above 0 km/h, and False otherwise (no GPS block, no fix, or no speed).

## Account notes

- Multi-factor login (the SMS code) isn't supported yet. If it's switched on for the account, `login()` raises `MgIndiaMfaRequired`. Switching it off in the MG app's security settings lets the client log in.
- MG India allows one login session per account. Logging in with the client signs the MG app out on the phone.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check src tests
```

## Release notes

### 1.0.0

- First stable API. Add `MgIndiaClient.for_vehicle()` for several cars on one account, the `status_timeout` constructor keyword (wait for the status request raised from 15 s to 45 s by default; the charging frame wait stays at 15 s), and `Status.is_moving`.

### 0.3.2

- Re-login when the gateway reports the session was taken over by another login (code 2).

### 0.3.0

- Add `Vehicle.is_electric`.
- Add `Snapshot.battery_soc`, using the charge frame's SOC or falling back to the status fuel level for EVs.
- Add `ChargeStatus.charging_power_kw`.
- Add `MgIndiaMfaRequired`, a subclass of `MgIndiaLoginRejected`, raised when the account has multi-factor login turned on.

### 0.2.1

- Reject malformed responses, mismatched vehicle identities and invalid charge values.
- Avoid resending commands when their completion is uncertain.
- Improve session recovery and verify lock outcomes against fresh vehicle status.

## License

MIT License. Copyright (c) 2026 John Lazarus.
