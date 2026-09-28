"""Replay published known pilots using the pinned DS7 production reader release."""

import dataclasses
import json
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score


def main():
    out = Path(__file__).parent / "local"
    inventory = json.loads((out / "inventory.json").read_text())
    rows = []
    for row in inventory["exports"]:
        raw = np.load(out / (row["name"] + ".npy"))
        c = row["candidate"]
        result = conditioned_glrt64_score(
            raw[:, 0].astype(float) + 1j * raw[:, 1],
            row["sample_rate_hz"],
            epoch_sample=c["integer_epoch_sample"],
            fractional_epoch_offset_samples=c["fractional_epoch_offset_samples"],
            acquired_cfo_hz=c["fractional_tracking_cfo_hz"],
            edge="upper",
        )
        rows.append(dict(name=row["name"], result=dataclasses.asdict(result)))
    (out / "pilot-replay.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
