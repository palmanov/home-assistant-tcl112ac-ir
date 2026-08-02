"""TCL112AC infrared encoder."""

import base64

MODES = {"heat": 1, "dry": 2, "cool": 3, "fan_only": 7, "auto": 8}
FANS = {"auto": 0, "min": 1, "low": 2, "medium": 3, "high": 5}
SWINGS = {"off": 0, "highest": 1, "high": 2, "middle": 3, "low": 4, "lowest": 5, "on": 7}

# Both frames were captured three times from the tested remote.
SPECIAL_PREFIX = bytes.fromhex("23 cb 26 02 00 40 20 00 03 00 00 00 00 88")
NORMAL_STATE = bytes.fromhex("23 cb 26 01 00 24 03 07 00 00 00 00 80 c3")


def generate_code(
    *,
    power: bool,
    mode: str,
    temperature: float,
    fan: str,
    swing: str,
) -> str:
    """Build a Tuya/Zosung Base64 IR code."""
    state = bytearray(NORMAL_STATE)

    if power:
        state[5] |= 0x04
    else:
        state[5] &= ~0x04

    state[6] = (state[6] & 0xF0) | MODES[mode]

    half_degrees = round(temperature * 2)
    state[7] = (state[7] & 0xF0) | (31 - half_degrees // 2)
    if half_degrees & 1:
        state[12] |= 0x20
    else:
        state[12] &= ~0x20

    fan_value = FANS["high"] if mode == "fan_only" else FANS[fan]
    state[8] = (state[8] & 0xF8) | fan_value
    state[8] = (state[8] & 0xC7) | (SWINGS[swing] << 3)
    state[-1] = sum(state[:-1]) & 0xFF

    timings = _state_to_timings(SPECIAL_PREFIX)
    timings.append(0xFFFF)
    timings.extend(_state_to_timings(state))
    return _encode_tuya_timings(timings)


def _state_to_timings(state: bytes) -> list[int]:
    timings = [3000, 1650]
    for byte in state:
        for bit in range(8):
            timings.extend((500, 1050 if byte & (1 << bit) else 325))
    timings.append(500)
    return timings


def _encode_tuya_timings(timings: list[int]) -> str:
    raw = bytearray()
    for timing in timings:
        raw.extend((timing & 0xFF, timing >> 8))

    encoded = bytearray()
    for pos in range(0, len(raw), 32):
        block = raw[pos : pos + 32]
        encoded.append(len(block) - 1)
        encoded.extend(block)
    return base64.b64encode(encoded).decode()
