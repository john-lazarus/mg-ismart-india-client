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
    # Only set this where a charging frame is expected. The loop waits for one,
    # so a vehicle that never sends it spends the full poll budget on every call.
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
