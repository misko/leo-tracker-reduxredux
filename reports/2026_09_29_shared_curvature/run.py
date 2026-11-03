import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from model import SharedCurvature
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402


def main(key, sigma):
    started = time.monotonic()
    paths = [
        HERE / "run.py",
        HERE / "model.py",
        HERE / "PROTOCOL.md",
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
        HERE.parent / "2026_09_29_sparse_waveform_position" / f"{key}.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
    ]
    plan, saved, recurrence = [json.loads(p.read_text()) for p in paths[3:]]
    for name, digest in saved["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
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
    docs = baseline.load_documents(dict(config=plan["config"], inputs=unit["group"]["inputs"]))
    old = saved["arms"]["cached"]["selected"]
    x = np.array(old["x"])
    model = SharedCurvature(docs, plan["config"], baseline.Stationary, {}, sigma)
    original = model.base.evaluate(x, held=True)
    assert abs(original["score"] - old["score"]) < 1e-7
    groups = {}
    rows = iter(original["rows"])
    for di, doc in enumerate(docs):
        for ti, track in enumerate(doc["tracks"]):
            row = next(rows)
            slot = int(np.argmax(row["weights_given_signal"]))
            if row["weights_given_signal"][slot] * row["signal_responsibility"] < 0.5:
                continue
            training_times = np.asarray(track["times_s"])[track["mask"]]
            if len(training_times) < 8 or np.ptp(training_times) < 10:
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

    def objective(z):
        out = model.evaluate(z)
        return -out["score"], -out["gradient"]

    bounds = [(-12.0, 12.0)] * 2 + [(-5.0, 5.0)] * len(docs)
    fit = minimize(
        objective,
        x,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25),
    )
    out = model.evaluate(fit.x, held=True)
    differences = []
    for i, step in enumerate([1e-4, 1e-4] + [1e-5] * len(docs)):
        p, m = fit.x.copy(), fit.x.copy()
        p[i] += step
        m[i] -= step
        numerical = (model.evaluate(p, False)["score"] - model.evaluate(m, False)["score"]) / (
            2 * step
        )
        differences.append(abs(numerical - out["gradient"][i]))
    model.order = 256
    audit = model.evaluate(fit.x, held=True)
    delta = dict(
        score=abs(out["score"] - audit["score"]),
        gradient=float(max(abs(out["gradient"] - audit["gradient"]))),
        held=abs(out["held_score"] - audit["held_score"]),
    )
    boundary = any(min(v - lo, hi - v) < 0.001 for v, (lo, hi) in zip(fit.x, bounds, strict=True))
    pg = float(max(abs(out["gradient"])))
    qualified = bool(
        fit.success
        and not boundary
        and pg <= 0.01
        and max(differences) <= 0.02
        and max(delta.values()) <= 0.01
    )
    common = model.base.evaluate(fit.x, gradient=False, held=True)
    result = dict(
        unit=key,
        sigma=sigma,
        groups=len(groups),
        grouped_tracks=len(model.membership),
        group_members=[
            dict(scan=k[0], number=k[1], rf_hz=k[2], members=v) for k, v in groups.items()
        ],
        x=fit.x.tolist(),
        success=bool(fit.success),
        message=str(fit.message),
        qualified=qualified,
        boundary=boundary,
        projected_gradient=pg,
        gradient_audit=max(differences),
        quadrature_audit=delta,
        score=out["score"],
        held_score=out["held_score"],
        baseline_held_score=sum(r["held_log_score"] for r in original["rows"]),
        common_held_score=sum(r["held_log_score"] for r in common["rows"]),
        estimate_deg=list(model.models[0].coordinates(fit.x[:3])),
        baseline_estimate_deg=old["estimate_deg"],
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / f"{key}_{sigma:g}.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(key, sigma, qualified, pg, delta, result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]))
