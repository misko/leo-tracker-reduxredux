"""Metadata-only protocol generation; never calls the native estimator."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    paths = [
        ROOT / "tools/native_presence.py",
        ROOT / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        HERE.parent / "2026_10_09_position_error_iter120/partial_signal.py",
    ]
    paths += list((ROOT / "src/leo/analysis/native_presence").glob("*"))
    paths += list((ROOT / "src/leo/analysis/starlink").glob("*.py"))
    paths += list(HERE.glob("*.py")) + [HERE / "PROTOCOL.md"]
    plan = {
        "schema": "iter122-offgrid-conditioned-v1",
        "phases_bins": [-0.4, -0.2, 0, 0.2, 0.4],
        "amplitudes": [0.25, 1],
        "cutoffs_s": [0.00015, 0.001, 0.020],
        "seeds": list(range(122000, 122016)),
        "margin_gate": 0.025,
        "native_call_cap": 480,
        "noise_rms": 1,
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))
            if p.is_file()
        },
    }
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
