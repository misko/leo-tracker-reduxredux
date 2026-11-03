import hashlib
import json
from pathlib import Path

import numpy as np
from model import predict, wrap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = HERE.parent / "2026_09_29_donor_residual_transfer"


def main():
    seal_path = SOURCE / "evidence-sha256.json"
    seal = json.loads(seal_path.read_text())["sha256"]
    plan_path = SOURCE / "plan.json"
    plan = json.loads(plan_path.read_text())
    cases = []
    hashes = {}
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        p = SOURCE / "runs" / u["unit_id"] / "result.json"
        name = str(p.relative_to(ROOT))
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        assert digest == seal[name]
        hashes[name] = digest
        for c in json.loads(p.read_text())["cases"]:
            e = np.asarray(c["residual"]) * c["rf_hz"] / 11.2e9
            mask = np.asarray(c["mask"], bool)
            center = float(np.mean(e[mask]))
            assert abs(center - c["shape"]["residual_center"] * c["rf_hz"] / 11.2e9) < 1e-7
            cases.append(dict(c, native_offset_hz=center, native_held=e[~mask].tolist()))
    assert len(cases) == 3983
    by_session = {}
    for c in cases:
        by_session.setdefault(c["session_id"], []).append(c)
    rows = []
    for c in cases:
        row = {
            k: c[k] for k in ("unit_id", "session_id", "track_id", "number", "receiver_id", "rf_hz")
        }
        held = np.array(c["native_held"])
        row["own_error_hz"] = float(np.median(abs(wrap(held - c["native_offset_hz"]))))
        row["arms"] = {}
        for name, opposite in (("same_rx", False), ("opposite_rx", True)):
            estimate = predict(c, by_session[c["session_id"]], opposite)
            if estimate is not None:
                estimate.update(
                    held_error_hz=float(np.median(abs(wrap(held - estimate["offset_hz"])))),
                    target_training_offset_difference_hz=abs(
                        float(wrap(c["native_offset_hz"] - estimate["offset_hz"]))
                    ),
                )
            row["arms"][name] = estimate
        rows.append(row)
    summary = {}
    for ds in ("DS7", "DS8", "DS9", "all"):
        selected = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        arms = {}
        for arm in ("same_rx", "opposite_rx"):
            valid = [r for r in selected if r["arms"][arm] is not None]
            own = np.array([r["own_error_hz"] for r in valid])
            shared = np.array([r["arms"][arm]["held_error_hz"] for r in valid])
            arms[arm] = dict(
                supported=len(valid),
                unsupported=len(selected) - len(valid),
                improved=int(sum(shared < own - 1e-6)),
                median_own_error_hz=float(np.median(own)) if valid else None,
                median_shared_error_hz=float(np.median(shared)) if valid else None,
                median_paired_gain_hz=float(np.median(own - shared)) if valid else None,
                median_training_offset_difference_hz=float(
                    np.median(
                        [r["arms"][arm]["target_training_offset_difference_hz"] for r in valid]
                    )
                )
                if valid
                else None,
                median_donor_dispersion_hz=float(
                    np.median([r["arms"][arm]["donor_median_deviation_hz"] for r in valid])
                )
                if valid
                else None,
            )
        summary[ds] = dict(cases=len(selected), arms=arms)
    for p in (seal_path, plan_path, HERE / "run.py", HERE / "model.py", HERE / "PROTOCOL.md"):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, rows=rows, summary=summary), indent=2, allow_nan=False)
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
