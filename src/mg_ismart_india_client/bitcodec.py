from __future__ import annotations

import math


class PackedBitReader:
    def __init__(self, data: bytes | bytearray) -> None:
        self.data = data
        self.offset = 0

    def read(self, count: int) -> int:
        value = 0
        for _ in range(count):
            absolute = self.offset
            self.offset += 1
            value = (value << 1) | (
                (self.data[absolute // 8] >> (7 - absolute % 8)) & 1
            )
        return value

    def read_string(self, minimum: int, maximum: int) -> str:
        span = maximum - minimum
        length = minimum + (self.read(math.ceil(math.log2(span + 1))) if span else 0)
        return "".join(chr(self.read(7)) for _ in range(length))


class PackedBitWriter:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def write(self, value: int, count: int) -> None:
        if value < 0 or value >= (1 << count):
            raise ValueError("bit value out of range")
        self.bits.extend((value >> shift) & 1 for shift in range(count - 1, -1, -1))

    def write_string(self, value: str, minimum: int, maximum: int) -> None:
        span = maximum - minimum
        if not minimum <= len(value) <= maximum:
            raise ValueError("string length out of range")
        if span:
            self.write(len(value) - minimum, math.ceil(math.log2(span + 1)))
        for char in value:
            self.write(ord(char), 7)

    def bytes(self) -> bytes:
        out = bytearray()
        for start in range(0, len(self.bits), 8):
            val = 0
            chunk = self.bits[start : start + 8]
            for bit in chunk:
                val = (val << 1) | bit
            out.append(val << (8 - len(chunk)))
        return bytes(out)


def set_msb_bits(buf: bytearray, offset: int, count: int, value: int) -> None:
    if value < 0 or value >= (1 << count):
        raise ValueError("bit value out of range")
    for idx in range(count):
        absolute = offset + idx
        mask = 1 << (7 - absolute % 8)
        if (value >> (count - 1 - idx)) & 1:
            buf[absolute // 8] |= mask
        else:
            buf[absolute // 8] &= ~mask


def set_fixed_7bit(buf: bytearray, offset: int, value: str) -> None:
    for idx, char in enumerate(value):
        set_msb_bits(buf, offset + idx * 7, 7, ord(char))


def read_msb_bits(buf: bytes | bytearray, offset: int, count: int) -> int:
    value = 0
    for idx in range(count):
        absolute = offset + idx
        value = (value << 1) | ((buf[absolute // 8] >> (7 - absolute % 8)) & 1)
    return value


def read_fixed_7bit(buf: bytes | bytearray, offset: int, count: int) -> str:
    return "".join(chr(read_msb_bits(buf, offset + idx * 7, 7)) for idx in range(count))
