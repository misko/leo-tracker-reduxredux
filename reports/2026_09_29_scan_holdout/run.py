import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REUSED = HERE.parent / "2026_09_29_receiver_holdout/run.py"
spec = importlib.util.spec_from_file_location("receiver_runner", REUSED)
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
from timing import marginal_scan  # noqa: E402


def split(docs, direction):
    if len(docs) != 8 or direction not in (0, 1):
        raise ValueError("Require eight scans and direction 0 or 1")
    return (docs[:4], docs[4:]) if direction == 0 else (docs[4:], docs[:4])


def main(key, direction):
    started = time.monotonic()
    paths = [
        HERE / "run.py",
        HERE / "timing.py",
        HERE / "PROTOCOL.md",
        REUSED,
        HERE.parent / "2026_09_29_shared_candidate_slope/model.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
    ]
    plan, recurrence = [json.loads(p.read_text()) for p in paths[-2:]]
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    for entry in unit["group"]["inputs"]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(p)
    docs = receiver.baseline.load_documents(
        dict(config=plan["config"], inputs=unit["group"]["inputs"])
    )
    source, target = split(docs, direction)
    train = receiver.TrendMixturePosition(source, plan["config"], receiver.baseline.Stationary, 0.2)
    test = [
        receiver.TrendMixturePosition([d], plan["config"], receiver.baseline.Stationary, 0.2)
        for d in target
    ]
    starts = []
    for east in (-2.0, 0.0, 2.0):
        x = np.zeros(6)
        x[0] = east
        starts.append(receiver.fit_model(train, x))
    valid = [r for r in starts if r["qualified"]]
    arms = []
    if valid:
        best = dict(max(valid, key=lambda r: r["score"]), sigma=0.0)
        x = np.array(best["x"])
        original = train.evaluate(x, gradient=False, held=True)
        best["source_held_score"] = sum(r["held_log_score"] for r in original["rows"])
        arms.append(best)
        groups = {}
        rows = iter(original["rows"])
        for di, doc in enumerate(source):
            for ti, track in enumerate(doc["tracks"]):
                row = next(rows)
                slot = int(np.argmax(row["weights_given_signal"]))
                if row["weights_given_signal"][slot] * row["signal_responsibility"] < 0.5:
                    continue
                number = int(mapping[doc["session_id"], track["track_id"]][slot])
                groups.setdefault((di, number), []).append((di, ti, slot))
        groups = {k: v for k, v in groups.items() if len(v) >= 2}
        membership = {
            (di, ti): (number, slot)
            for (_, number), members in groups.items()
            for di, ti, slot in members
        }
        model = receiver.SharedSlope(
            source, plan["config"], receiver.baseline.Stationary, membership, 0.5
        )
        fitted = receiver.fit_model(model, x)
        z = np.array(fitted["x"])
        out = model.evaluate(z, held=True)
        model.order = 256
        audit = model.evaluate(z, held=True)
        delta = dict(
            score=abs(out["score"] - audit["score"]),
            held=abs(out["held_score"] - audit["held_score"]),
            gradient=float(max(abs(out["gradient"] - audit["gradient"]))),
        )
        fitted.update(
            sigma=0.5,
            qualified=fitted["qualified"] and max(delta.values()) <= 0.01,
            quadrature_audit=delta,
            groups=len(groups),
            grouped_tracks=len(membership),
            source_held_score=out["held_score"],
        )
        arms.append(fitted)
        for arm in arms:
            arm["estimate_deg"] = list(train.models[0].coordinates(arm["x"][:3]))
            arm["target_scans"] = [
                dict(session_id=d["session_id"], **marginal_scan(m, arm["x"][:2]))
                for d, m in zip(target, test, strict=True)
            ]
            arm["target_log_score"] = sum(r["log_score"] for r in arm["target_scans"])
            arm["qualified"] &= all(r["qualified"] for r in arm["target_scans"])
    result = dict(
        unit=key,
        direction=direction,
        source_sessions=[d["session_id"] for d in source],
        target_sessions=[d["session_id"] for d in target],
        baseline_starts=starts,
        arms=arms,
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / f"{key}_d{direction}.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(key, direction, [r["qualified"] for r in arms], result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
