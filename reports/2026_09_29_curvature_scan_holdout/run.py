import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


receiver = module("receiver_runner", REPORTS / "2026_09_29_receiver_holdout/run.py")
curvature = module("curvature_model", REPORTS / "2026_09_29_shared_curvature/model.py")
timing = module("scan_timing", REPORTS / "2026_09_29_scan_holdout/timing.py")


def marginal(model, position):
    result = timing.marginal_scan(model, position)
    if not result["qualified"]:
        initial = result.copy()
        values = []
        for order in (64, 128):
            nodes, weights = timing.timing_nodes(order, model.models[0].taus)
            values.append(timing.log_integral(timing.full_scores(model, position, nodes), weights))
        result.update(
            initial=initial,
            log_score=values[0],
            audit_log_score=values[1],
            quadrature_difference=abs(values[0] - values[1]),
            qualified=bool(abs(values[0] - values[1]) <= 0.01),
        )
    return result


def main(key, direction):
    started = time.monotonic()
    paths = [
        HERE / "run.py",
        HERE / "PROTOCOL.md",
        REPORTS / "2026_09_29_shared_curvature/model.py",
        REPORTS / "2026_09_29_receiver_holdout/run.py",
        REPORTS / "2026_09_29_scan_holdout/timing.py",
        REPORTS / "2026_09_29_unassociated_trend/trend_mixture.py",
        REPORTS / "2026_09_29_frequency_contrast/contrast_position.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        REPORTS / f"2026_09_29_scan_holdout/{key}_d{direction}.json",
        REPORTS / "2026_09_29_donor_residual_transfer/plan.json",
        REPORTS / "2026_09_29_catalogue_recurrence/result.json",
    ]
    old, plan, recurrence = [json.loads(p.read_text()) for p in paths[-3:]]
    for name, h in old["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    for entry in unit["group"]["inputs"]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(p)
    docs = receiver.baseline.load_documents(
        dict(config=plan["config"], inputs=unit["group"]["inputs"])
    )
    source, target = (docs[:4], docs[4:]) if direction == 0 else (docs[4:], docs[:4])
    assert [d["session_id"] for d in source] == old["source_sessions"]
    assert [d["session_id"] for d in target] == old["target_sessions"]
    assert not set(old["source_sessions"]) & set(old["target_sessions"])
    base = dict(old["arms"][0])
    x = np.array(base["x"])
    assert (
        base["success"]
        and not base["boundary"]
        and base["projected_gradient"] <= 0.01
        and base["gradient_audit"] <= 0.02
    )
    train = receiver.TrendMixturePosition(source, plan["config"], receiver.baseline.Stationary, 0.2)
    original = train.evaluate(x, held=True)
    assert abs(original["score"] - base["score"]) < 1e-7
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    groups = {}
    rows = iter(original["rows"])
    for di, doc in enumerate(source):
        for ti, track in enumerate(doc["tracks"]):
            r = next(rows)
            slot = int(np.argmax(r["weights_given_signal"]))
            times = np.asarray(track["times_s"])[track["mask"]]
            if (
                r["weights_given_signal"][slot] * r["signal_responsibility"] < 0.5
                or len(times) < 8
                or np.ptp(times) < 10
            ):
                continue
            number = int(mapping[doc["session_id"], track["track_id"]][slot])
            groups.setdefault((di, number, float(track["rf_hz"])), []).append((di, ti, slot))
    groups = {
        k: v
        for k, v in groups.items()
        if len(v) >= 2 and {source[di]["tracks"][ti]["receiver_id"] for di, ti, _ in v} == {0, 1}
    }
    membership = {
        (di, ti): ((number, rf), slot)
        for (_, number, rf), members in groups.items()
        for di, ti, slot in members
    }
    model = curvature.SharedCurvature(
        source, plan["config"], receiver.baseline.Stationary, membership, 0.1
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
        qualified=bool(fitted["qualified"] and max(delta.values()) <= 0.01),
        quadrature_audit=delta,
        source_held_score=out["held_score"],
    )
    base["qualified"] = True
    arms = [base, fitted]
    for arm in arms:
        arm["estimate_deg"] = list(train.models[0].coordinates(arm["x"][:3]))
        arm["target_scans"] = []
        for doc in target:
            test = receiver.TrendMixturePosition(
                [doc], plan["config"], receiver.baseline.Stationary, 0.2
            )
            arm["target_scans"].append(
                dict(session_id=doc["session_id"], **marginal(test, arm["x"][:2]))
            )
        arm["target_log_score"] = sum(r["log_score"] for r in arm["target_scans"])
        arm["qualified"] = bool(
            arm["qualified"] and all(r["qualified"] for r in arm["target_scans"])
        )
    result = dict(
        unit=key,
        direction=direction,
        source_sessions=old["source_sessions"],
        target_sessions=old["target_sessions"],
        arms=arms,
        groups=len(groups),
        grouped_tracks=len(membership),
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    with (HERE / f"{key}_d{direction}.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(key, direction, [a["qualified"] for a in arms], result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
