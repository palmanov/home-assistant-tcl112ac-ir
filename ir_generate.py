#!/usr/bin/env python3
import argparse
import base64
import json


MODES = {"heat": 1, "dry": 2, "cool": 3, "fan": 7, "auto": 8}
FANS = {"auto": 0, "min": 1, "low": 2, "medium": 3, "high": 5}
SWING_VERTICAL = {
    "off": 0,
    "highest": 1,
    "high": 2,
    "middle": 3,
    "low": 4,
    "lowest": 5,
    "on": 7,
}

# This prefix was present in all three captures from the original remote.
CAPTURED_SPECIAL_PREFIX = bytes.fromhex("23 cb 26 02 00 40 20 00 03 00 00 00 00 88")
CAPTURED_NORMAL_STATE = bytes.fromhex("23 cb 26 01 00 24 03 07 00 00 00 00 80 c3")


def make_state(args: argparse.Namespace) -> bytes:
    state = bytearray(CAPTURED_NORMAL_STATE)

    if args.power == "on":
        state[5] |= 0x04
    else:
        state[5] &= ~0x04

    state[6] = (state[6] & 0xF0) | MODES[args.mode]

    half_degrees = round(args.temperature * 2)
    state[7] = (state[7] & 0xF0) | (31 - half_degrees // 2)
    if half_degrees & 1:
        state[12] |= 0x20
    else:
        state[12] &= ~0x20

    fan = FANS[args.fan]
    if args.mode == "fan":
        fan = FANS["high"]
    state[8] = (state[8] & 0xF8) | fan
    state[8] = (state[8] & 0xC7) | (SWING_VERTICAL[args.swing] << 3)

    if args.swing_horizontal == "on":
        state[12] |= 0x08
    else:
        state[12] &= ~0x08

    state[-1] = sum(state[:-1]) & 0xFF
    return bytes(state)


def state_to_timings(state: bytes) -> list[int]:
    timings = [3000, 1650]
    for byte in state:
        for bit in range(8):
            timings.extend((500, 1050 if byte & (1 << bit) else 325))
    timings.append(500)
    return timings


def encode_tuya_timings(timings: list[int]) -> str:
    raw = bytearray()
    for timing in timings:
        raw.extend((timing & 0xFF, timing >> 8))

    # Literal blocks are less compact than captures but are the canonical
    # encoding produced by current zigbee-herdsman-converters.
    encoded = bytearray()
    for pos in range(0, len(raw), 32):
        block = raw[pos : pos + 32]
        encoded.append(len(block) - 1)
        encoded.extend(block)
    return base64.b64encode(encoded).decode()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a TCL112AC IR code")
    parser.add_argument("--power", choices=("on", "off"), default="on")
    parser.add_argument("--mode", choices=MODES, default="cool")
    parser.add_argument("--temperature", type=float, default=24)
    parser.add_argument("--fan", choices=FANS, default="auto")
    parser.add_argument("--swing", choices=SWING_VERTICAL, default="off")
    parser.add_argument("--swing-horizontal", choices=("on", "off"), default="off")
    parser.add_argument(
        "--no-special-prefix",
        action="store_true",
        help="send only the normal TCL112AC state frame",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the complete Zigbee2MQTT JSON payload",
    )
    args = parser.parse_args()
    if not 16 <= args.temperature <= 31 or args.temperature * 2 % 1:
        parser.error("--temperature must be between 16 and 31 in 0.5 degree steps")
    return args


def main() -> None:
    args = parse_args()
    state = make_state(args)
    timings = []
    if not args.no_special_prefix:
        timings.extend(state_to_timings(CAPTURED_SPECIAL_PREFIX))
        timings.append(0xFFFF)
    timings.extend(state_to_timings(state))
    code = encode_tuya_timings(timings)

    if args.json:
        print(json.dumps({"ir_code_to_send": code}, separators=(",", ":")))
    else:
        print(code)


if __name__ == "__main__":
    main()
