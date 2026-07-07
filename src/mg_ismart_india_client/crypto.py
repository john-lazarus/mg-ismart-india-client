from __future__ import annotations

import hashlib
import hmac
import re
from binascii import unhexlify
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


class MgIndiaApiError(Exception):
    pass


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) >= 10:
        digits = digits[-10:]
    if len(digits) != 10:
        raise MgIndiaApiError("Use the 10 digit India mobile number")
    return digits


def make_device_id(phone: str) -> str:
    seed = hashlib.sha256(
        f"mg-ismart-india:{normalize_phone(phone)}".encode()
    ).hexdigest()
    return (f"haos-mg-ismart-india-{seed}" + "0" * 120)[:103]


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()  # noqa: S324 - MG India protocol compatibility


def tap_signature(body: str) -> str:
    key = md5_hex(body[1 : len(body) // 2])
    return hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()


def gateway_signature(
    path: str, timestamp: str, content_type: str = "application/json"
) -> str:
    part1 = md5_hex(path)
    part2 = md5_hex(part1 + timestamp + "1" + content_type)
    key = md5_hex(part2 + timestamp)
    return hmac.new(
        key.encode(), (path + timestamp + "1" + content_type).encode(), hashlib.sha256
    ).hexdigest()


def hash_control_pin(pin: str) -> str:
    if not re.fullmatch(r"\d{4}", pin or ""):
        raise MgIndiaApiError("Control PIN must be exactly 4 digits")
    return md5_hex(f"{pin}00").upper()


def decrypt_gateway_body(encrypted: str, headers: Any) -> str:
    timestamp = headers.get("APP-SEND-DATE") or headers.get("app-send-date") or ""
    content_type = (
        headers.get("ORIGINAL-CONTENT-TYPE")
        or headers.get("original-content-type")
        or "application/json"
    )
    key = md5_hex(timestamp + "1" + content_type)
    iv = md5_hex(timestamp)
    return unpad(
        AES.new(unhexlify(key), AES.MODE_CBC, unhexlify(iv)).decrypt(
            unhexlify(encrypted)
        ),
        AES.block_size,
    ).decode()
