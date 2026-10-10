"""Metadata-only declaration; does not build or call the estimator."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    paths = [ROOT / "tools/native_presence.py"]
    paths += [ROOT / "src/leo/analysis/starlink/_native_acquisition_grid.inc"]
    paths += list((ROOT / "src/leo/analysis/native_presence").glob("*"))
    paths += list((ROOT / "src/leo/analysis/starlink").glob("*.py"))
    paths += list(HERE.glob("*.py")) + [HERE / "SYNTHETIC_PROTOCOL.md"]
    plan = {
        "schema": "iter120-conditioned-synthetic-v1",
        "cutoffs_s": [0, 0.00015, 0.001, 0.005, 0.020],
        "amplitudes": [0.25, 1],
        "noise_rms": 1,
        "margin_gate": 0.025,
        "seeds": list(range(120000, 120016)),
        "native_call_cap": 160,
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))
            if p.is_file()
        },
    }
    with (HERE / "synthetic-protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
