"""Reuse the bounded native-rate decoder on the pilot-selected DS9 visit."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE.parent / "2026_09_28_ds7_ds8_correspondence"))
from native_rate_decode import recover  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="first")
    args = parser.parse_args()
    folder = BASE / f"local/ds9-{args.tag}-10m"
    inventory = folder / "inventory.json"
    out = BASE / f"local/DS9-{args.tag}-soft.npz"
    if out.exists():
        raise FileExistsError("Retain existing soft cache")
    arrays = dict(inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest())
    rows = []
    for index, row in enumerate(json.loads(inventory.read_text())["exports"]):
        bins, z, metadata = recover(row, folder, frame_limit=90)
        arrays.update(
            {f"bins{index}": bins, f"z{index}": z, f"metadata{index}": json.dumps(metadata)}
        )
        frames = [
            f
            for f in metadata["evaluation_frames"]
            if metadata["diagnostics"][f]["held_pilot_coherence"] > 0.5
        ]
        q = z.imag**2 / np.maximum(abs(z) ** 2, 1e-20)
        rows.append(
            dict(
                receiver=index,
                frames=len(z),
                carriers=len(bins),
                pilot_qualified_evaluation_frames=frames,
                mean_tail_q=None if not frames else float(q[frames, -10:].mean()),
            )
        )
        print(rows[-1], flush=True)
    np.savez_compressed(out, **arrays)
    result = dict(
        rows=rows,
        inventory_sha256=arrays["inventory_sha256"],
        output_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        limitation="One pilot-selected DS9 visit; tail quality diagnostic only. "
        "Not phase-boundary validation or decoded semantic bits.",
    )
    (BASE / f"local/ds9_{args.tag}_quality.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
