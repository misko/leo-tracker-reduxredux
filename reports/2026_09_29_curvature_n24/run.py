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
REUSED = REPORTS / "2026_09_29_curvature_scan_holdout/run.py"
spec = importlib.util.spec_from_file_location("holdout_runner", REUSED)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def read(path):
    return json.loads(path.read_text())


def main(ds):
    started = time.monotonic()
    paths = [
        HERE / "run.py",
        HERE / "PROTOCOL.md",
        REUSED,
        REPORTS / "2026_09_29_shared_curvature/model.py",
        REPORTS / "2026_09_29_receiver_holdout/run.py",
        REPORTS / "2026_09_29_scan_holdout/timing.py",
        REPORTS / "2026_09_29_unassociated_trend/trend_mixture.py",
        REPORTS / "2026_09_29_frequency_contrast/contrast_position.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        REPORTS / "2026_09_29_scan_budget/manifest.json",
        REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json",
        REPORTS / "2026_09_29_out_of_pool/manifest.json",
        REPORTS / "2026_09_29_catalogue_recurrence/result.json",
    ]
    manifest, baseline, targets, recurrence = [read(p) for p in paths[-4:]]
    for prior in (baseline, manifest, targets):
        for name, h in prior["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    inputs = [s["input"] for s in pool["scans"]]
    selected_targets = [s for s in targets["sets"] if s["dataset"] == ds]
    assert len(selected_targets) == 5
    for entry in inputs + [s["input"] for s in selected_targets]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(p)
    receiver = helper.receiver
    docs = receiver.baseline.load_documents(dict(config=manifest["config"], inputs=inputs))
    assert [d["session_id"] for d in docs] == baseline["sessions"]
    assert not set(baseline["sessions"]) & {s["input"]["session_id"] for s in selected_targets}
    old = baseline["selected"]
    assert old["qualified"]
    x = np.array(old["x"])
    model = helper.curvature.SharedCurvature(
        docs, manifest["config"], receiver.baseline.Stationary, {}, 0.1
    )
    original = model.base.evaluate(x, held=True)
    assert abs(original["score"] - old["score"]) < 1e-7
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    groups = {}
    rows = iter(original["rows"])
    for di, doc in enumerate(docs):
        for ti, track in enumerate(doc["tracks"]):
            row = next(rows)
            slot = int(np.argmax(row["weights_given_signal"]))
            t = np.asarray(track["times_s"])[track["mask"]]
            if (
                row["weights_given_signal"][slot] * row["signal_responsibility"] < 0.5
                or len(t) < 8
                or np.ptp(t) < 10
            ):
                continue
            number = int(mapping[doc["session_id"], track["track_id"]][slot])
            groups.setdefault((di, number, float(track["rf_hz"])), []).append((di, ti, slot))
    groups = {
        k: v
        for k, v in groups.items()
        if len(v) >= 2 and {docs[di]["tracks"][ti]["receiver_id"] for di, ti, _ in v} == {0, 1}
    }
    model.membership = {
        (di, ti): ((number, rf), slot)
        for (_, number, rf), members in groups.items()
        for di, ti, slot in members
    }
    fit = receiver.fit_model(model, x)
    z = np.array(fit["x"])
    out = model.evaluate(z, held=True)
    model.order = 256
    audit = model.evaluate(z, held=True)
    delta = dict(
        score=abs(out["score"] - audit["score"]),
        held=abs(out["held_score"] - audit["held_score"]),
        gradient=float(max(abs(out["gradient"] - audit["gradient"]))),
    )
    fit.update(
        qualified=bool(fit["qualified"] and max(delta.values()) <= 0.01),
        quadrature_audit=delta,
        estimate_deg=list(model.models[0].coordinates(z[:3])),
        source_held_score=out["held_score"],
    )
    results = []
    for target in selected_targets:
        oldpath = REPORTS / f"2026_09_29_out_of_pool/{target['unit']}.json"
        paths.append(oldpath)
        prior = read(oldpath)
        assert all(v["qualified"] for v in prior["values"])
        assert prior["session_id"] == target["input"]["session_id"]
        assert (
            prior["manifest_sha256"]
            == hashlib.sha256(
                (REPORTS / "2026_09_29_out_of_pool/manifest.json").read_bytes()
            ).hexdigest()
        )
        testdocs = receiver.baseline.load_documents(
            dict(config=manifest["config"], inputs=[target["input"]])
        )
        test = receiver.TrendMixturePosition(
            testdocs, manifest["config"], receiver.baseline.Stationary, 0.2
        )
        results.append(
            dict(
                unit=target["unit"],
                session_id=prior["session_id"],
                prior_values=prior["values"],
                **helper.marginal(test, z[:2]),
            )
        )
    result = dict(
        dataset=ds,
        fit=fit,
        baseline=old,
        source_sessions=baseline["sessions"],
        start_span_hours=pool["start_span_hours"],
        groups=len(groups),
        grouped_tracks=len(model.membership),
        targets=results,
        qualified=bool(fit["qualified"] and all(r["qualified"] for r in results)),
        source_baseline_held_score=sum(r["held_log_score"] for r in original["rows"]),
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    with (HERE / f"{ds}.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(ds, result["qualified"], fit["message"], result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
