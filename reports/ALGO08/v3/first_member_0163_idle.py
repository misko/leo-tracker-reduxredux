"""One preregistered low-I/O slot for the exact first DS30-0163 member."""

import argparse
import json
from pathlib import Path

from first_member_0419 import metadata, select_first
from first_member_0419_idle import BLOCK, DEVICE, HERE, IDLE_PIN, RATE, stage


CASE = "DS30-0163"
READY = Path("/dev/shm/leo-v3-ds30-0163-ready01")
PREVIOUS = HERE / "measurements/ds30-combined-first-member-admission.json"
PREVIOUS_PIN = "0534f23e9f8cbf56ad51301c8a64f765f212782acfbdeedf883d188221c5b74a"
REQUEST_PIN = "654bb406870bd97ac6b1854f312b0dae54e8405d6fda81c2ee135c61e41fcae9"
INVENTORY_PIN = "d30888ead13433a1194dec7286e2a71af3d4d78876733eadd8becc06c7121ddd"
SIZE, SECONDS = 78_720_466, 300


def bindings():
    metadata(HERE / "guarded_stage_idle.py", IDLE_PIN, 20_000)
    old, = (row for row in json.loads(metadata(PREVIOUS, PREVIOUS_PIN, 80_000))["cases"] if row["case"] == CASE)
    req = json.loads(metadata(READY / "request.json", REQUEST_PIN, 96_000))
    inv = json.loads(metadata(READY / "inventory.json", INVENTORY_PIN, 96_000))
    original, first = select_first(req, inv, case=CASE, inventory_pin=INVENTORY_PIN)
    member = old["first_member"]
    if (first != old["signed_first_segment"] or member["compressed_bytes"] != SIZE or member["window_count"] != 64
            or old["cache"]["device"] != DEVICE or member["first_sequence"] != 0
            or (BLOCK, RATE) != (1_048_576, 2_097_152) or original.resolve(strict=True) != original):
        raise ValueError("The original first-member enrollment changed")
    payload = original / member["payload_relative_path"]
    if payload.resolve(strict=True) != payload:
        raise ValueError("The selected payload traverses a symlink")
    return req, first, member, payload, old["cache"]["inode"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output
    stage(output, bind=bindings, case=CASE, previous_pin=PREVIOUS_PIN, request_pin=REQUEST_PIN,
          inventory_pin=INVENTORY_PIN, size=SIZE, seconds=SECONDS)
