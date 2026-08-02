#!/usr/bin/env python3
import base64
import sys
from pathlib import Path


MODES = {1: "HEAT", 2: "DRY", 3: "COOL", 7: "FAN", 8: "AUTO"}
FANS = {0: "AUTO", 1: "MIN", 2: "LOW", 3: "MEDIUM", 5: "HIGH"}
SWING_VERTICAL = {
    0: "OFF",
    1: "HIGHEST",
    2: "HIGH",
    3: "MIDDLE",
    4: "LOW",
    5: "LOWEST",
    7: "ON",
}


def decode_tuya_timings(value: str) -> list[int]:
    compressed = base64.b64decode(value)
    decompressed = bytearray()
    pos = 0

    while pos < len(compressed):
        header = compressed[pos]
        pos += 1
        block_type = header >> 5

        if block_type == 0:
            length = (header & 0x1F) + 1
            decompressed.extend(compressed[pos : pos + length])
            pos += length
            continue

        length = block_type + 2
        if length == 9:
            while compressed[pos] == 0xFF:
                length += 255
                pos += 1
            length += compressed[pos]
            pos += 1

        distance = (((header & 0x1F) << 8) | compressed[pos]) + 1
        pos += 1
        for _ in range(length):
            decompressed.append(decompressed[-distance])

    return [
        decompressed[pos] | (decompressed[pos + 1] << 8)
        for pos in range(0, len(decompressed) - 1, 2)
    ]


def split_frames(timings: list[int]) -> list[list[int]]:
    frames = []
    start = 0
    for pos, timing in enumerate(timings):
        if timing >= 10_000:
            frames.append(timings[start:pos])
            start = pos + 1
    if start < len(timings):
        frames.append(timings[start:])
    return [frame for frame in frames if frame]


def decode_tcl112(frame: list[int]) -> bytes:
    if len(frame) != 227:
        raise ValueError(f"expected 227 timings, got {len(frame)}")

    bits = [int(frame[pos] > 700) for pos in range(3, len(frame), 2)]
    if len(bits) != 112:
        raise ValueError(f"expected 112 bits, got {len(bits)}")

    return bytes(
        sum(bits[start + bit] << bit for bit in range(8))
        for start in range(0, len(bits), 8)
    )


def describe_tcl112(state: bytes) -> str:
    checksum_offset = 0x0F if state[3] == 2 else 0
    expected_checksum = (sum(state[:-1]) + checksum_offset) & 0xFF
    message_type = {1: "normal", 2: "special"}.get(state[3] & 0x03, "unknown")

    if message_type == "special":
        return (
            f"type={message_type}, checksum={'OK' if state[-1] == expected_checksum else 'BAD'}"
        )

    temperature = 31 - (state[7] & 0x0F)
    if state[12] & 0x20:
        temperature += 0.5

    values = {
        "type": message_type,
        "power": "ON" if state[5] & 0x04 else "OFF",
        "mode": MODES.get(state[6] & 0x0F, f"UNKNOWN({state[6] & 0x0F})"),
        "temperature": f"{temperature:g}C",
        "fan": FANS.get(state[8] & 0x07, f"UNKNOWN({state[8] & 0x07})"),
        "swing_v": SWING_VERTICAL.get(
            (state[8] >> 3) & 0x07, f"UNKNOWN({(state[8] >> 3) & 0x07})"
        ),
        "swing_h": "ON" if state[12] & 0x08 else "OFF",
        "quiet_bit": "SET" if state[5] & 0x20 else "CLEAR",
        "turbo": "ON" if state[6] & 0x20 else "OFF",
        "eco": "ON" if state[5] & 0x80 else "OFF",
        "health": "ON" if state[6] & 0x10 else "OFF",
        "light": "OFF" if state[5] & 0x40 else "ON",
        "checksum": "OK" if state[-1] == expected_checksum else "BAD",
    }
    return ", ".join(f"{key}={value}" for key, value in values.items())


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "captures.txt")
    captures = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ": " in line:
            label, value = line.split(": ", 1)
        else:
            label, value = "", line
        captures.append((label, value))

    for capture_number, (label, value) in enumerate(captures, 1):
        timings = decode_tuya_timings(value)
        suffix = f" ({label})" if label else ""
        print(f"capture {capture_number}{suffix}: {len(timings)} timings")
        for frame_number, frame in enumerate(split_frames(timings), 1):
            state = decode_tcl112(frame)
            print(f"  frame {frame_number}: {state.hex(' ')}")
            print(f"    {describe_tcl112(state)}")


if __name__ == "__main__":
    main()
