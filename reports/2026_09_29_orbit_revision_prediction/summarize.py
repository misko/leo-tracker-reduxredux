"""Audit revision accounting and report all, supported and changed subsets."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def summary(rows, arm):
    gain = np.asarray([r["baseline_error"] - r["arms"][arm]["held_error"] for r in rows])
    changes = [
        r["arms"][arm]["revision_centered_rms_hz"] for r in rows if r["arms"][arm]["status"] == "ok"
    ]
    return dict(
        cases=len(rows),
        wins=int((gain > 1e-6).sum()),
        losses=int((gain < -1e-6).sum()),
        median_gain_hz=float(np.median(gain)) if len(gain) else None,
        mean_gain_hz=float(np.mean(gain)) if len(gain) else None,
        median_revision_shape_rms_hz=float(np.median(changes)) if changes else None,
    )


def main():
    result = json.loads((HERE / "results.json").read_text())
    for path, digest in result["hashes"].items():
        assert hashlib.sha256((HERE.parent.parent / path).read_bytes()).hexdigest() == digest
    rows = result["rows"]
    assert len({(r["unit_id"], r["session_id"], r["track_id"], r["number"]) for r in rows}) == 3983
    output = {}
    for ds in ("all", "DS7", "DS8", "DS9"):
        selected = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        output[ds] = {}
        for arm in ("older_6h", "older_24h"):
            supported = [r for r in selected if r["arms"][arm]["status"] == "ok"]
            changed = [r for r in supported if r["arms"][arm]["changed"]]
            for r in selected:
                a = r["arms"][arm]
                if a["status"] != "ok":
                    assert a["held_error"] == r["baseline_error"]
                elif not a["changed"]:
                    assert abs(a["held_error"] - r["baseline_error"]) < 1e-6
            output[ds][arm] = dict(
                all=summary(selected, arm),
                supported=summary(supported, arm),
                changed=summary(changed, arm),
                missing=sum(r["arms"][arm]["status"] == "missing" for r in selected),
                propagation_failures=sum(
                    r["arms"][arm]["status"] == "propagation_failure" for r in selected
                ),
            )
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        "Baseline replay:", result["max_baseline_difference"], "seconds", result["elapsed_seconds"]
    )
    for ds in output:
        for arm in output[ds]:
            print(ds, arm, output[ds][arm]["changed"])


if __name__ == "__main__":
    main()
