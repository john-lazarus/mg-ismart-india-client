# MG iSMART India Client

Python client for the MG iSMART India TAP/gateway API.

This package contains the protocol/client layer used by the MG iSMART India Home Assistant work. It is intentionally separate from Home Assistant so it can be tested and released independently.

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
    # Only set this where a charging frame is actually expected. The loop waits
    # for one, so when none comes it spends the full budget -- up to 10 POSTs
    # and ~13.5s -- on EVERY call. On an ICE vehicle, or a secondary account
    # whose charging telemetry is disabled server-side, that is the guaranteed
    # cost of every refresh, for nothing. Gate it on a known-EV flag rather
    # than turning it on by default.
    status = await client.status(include_charge=True)
    print(status.charge)
```

Control methods require a configured PIN hash. The raw 4-digit control PIN is not stored by the client.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check src tests
```

## License

MIT License. Copyright (c) 2026 John Lazarus.
