#!/usr/bin/env python3
"""Run the missing fixed-identity common fractional-tau diagnostic on DS1.

This deliberately limits new computation to the first TRAIN block's 16-scan
view.  Full-block duration behaviour is already provenance-bound in
``timing_rows.json``; this run tests timing resolution without per-track tau.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("timing_ablations", HERE / "run.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def main():
    case = next(x for x in module.cases() if x["case_id"] == "train_20260921_00_16")
    rows = []
    for prior in ("sacramento", "reno"):
        rows.extend(
            x
            for x in module.infer(case, prior, ())
            if x["model"]
            in {
                "fixed_identity_tau0",
                "fixed_identity_shared_global_tau",
                "fractional_common_global_tau_diagnostic",
            }
        )
    out = {
        "schema": "ds1-common-fractional-timing-diagnostic/v1",
        "rows": rows,
        "scope": "nested first-TRAIN 16-scan view; common global tau only",
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
        "bindings": {
            "source": module.digest(HERE / "run.py"),
            "dataset": module.digest(module.DATA),
        },
    }
    path = HERE / "fractional_diagnostic.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    print(json.dumps({"rows": len(rows), "models": sorted({x["model"] for x in rows})}, indent=2))


if __name__ == "__main__":
    main()
