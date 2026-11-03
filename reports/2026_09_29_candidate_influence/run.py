import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(HERE.parent / "2026_09_29_observation_influence")]
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from model import terms  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


class Weighted:
    def __init__(self, full, selected, weight):
        self.full, self.selected, self.weight = full, selected, weight

    def evaluate(self, x, gradient=True):
        a = self.full.evaluate(x, gradient=gradient)
        b = self.selected.evaluate(x, gradient=gradient)
        return dict(
            score=a["score"] + (self.weight - 1) * b["score"],
            gradient=a["gradient"] + (self.weight - 1) * b["gradient"],
        )


def response(hessian, gradient, change):
    return np.linalg.solve(hessian, gradient)[:2] * change * 1000


def main(key):
    started = time.monotonic()
    paths = [
        HERE / "run.py",
        HERE / "PROTOCOL.md",
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
        HERE.parent / "2026_09_29_observation_influence" / f"{key}.json",
        HERE.parent / "2026_09_29_sparse_waveform_position" / f"{key}.json",
    ]
    plan, recurrence, influence, saved = [json.loads(p.read_text()) for p in paths[2:]]
    for source in (influence, saved):
        for name, digest in source["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents(dict(config=plan["config"], inputs=unit["group"]["inputs"]))
    for entry in unit["group"]["inputs"]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(p)
    model = TrendMixturePosition(docs, plan["config"], baseline.Stationary, 0.2)
    old = saved["arms"]["cached"]["selected"]
    x = np.array(old["x"])
    hessian = np.array(influence["hessian"])
    assert influence["hessian_qualified"]
    original = model.evaluate(x, held=True)
    assert abs(original["score"] - old["score"]) < 1e-7
    lookup = {(r["session_id"], r["track_id"]): r for r in original["rows"]}
    groups, total = {}, np.zeros_like(x)
    for di, (doc, engine) in enumerate(zip(docs, model.models, strict=True)):
        local = x[[0, 1, di + 2]]
        for ti, track in enumerate(doc["tracks"]):
            mask = track["mask"]
            prediction, visible = engine.prediction(track, local)
            derivatives = []
            for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
                p, m = local.copy(), local.copy()
                p[axis] += step
                m[axis] -= step
                pp, vp = engine.prediction(track, p)
                pm, vm = engine.prediction(track, m)
                assert np.array_equal(vp, visible) and np.array_equal(vm, visible)
                derivatives.append((pp[visible][:, mask] - pm[visible][:, mask]) / (2 * step))
            _, g, _ = terms(
                track["y"][mask],
                np.array(track["times_s"])[mask],
                prediction[visible][:, mask],
                np.stack(derivatives, axis=2),
            )
            full_g = np.zeros_like(x)
            full_g[[0, 1, di + 2]] = g
            total += full_g
            row = lookup[doc["session_id"], track["track_id"]]
            k = int(np.argmax(row["weights_given_signal"]))
            if row["weights_given_signal"][k] * row["signal_responsibility"] < 0.5:
                continue
            number = int(mapping[doc["session_id"], track["track_id"]][k])
            groups.setdefault(number, []).append(
                dict(
                    di=di,
                    ti=ti,
                    session_id=doc["session_id"],
                    track_id=track["track_id"],
                    gradient=full_g.tolist(),
                )
            )
    replay = float(max(abs(total - original["gradient"])))
    assert replay < 1e-7
    ranked = []
    for number, members in groups.items():
        scans = sorted({r["di"] for r in members})
        if len(members) < 2:
            continue
        gradient = np.sum([r["gradient"] for r in members], axis=0)
        movement = response(hessian, gradient, -0.5)
        ranked.append(
            dict(
                number=number,
                members=members,
                gradient=gradient.tolist(),
                scans=scans,
                predicted_half_weight_m=movement.tolist(),
                magnitude_m=float(np.linalg.norm(movement)),
            )
        )
    ranked.sort(key=lambda r: (-r["magnitude_m"], r["number"]))
    assert ranked
    selected = ranked[0]
    keys = {(r["di"], r["ti"]) for r in selected["members"]}
    selected_docs = [
        dict(d, tracks=[t for ti, t in enumerate(d["tracks"]) if (di, ti) in keys])
        for di, d in enumerate(docs)
    ]
    subset = TrendMixturePosition(selected_docs, plan["config"], baseline.Stationary, 0.2)
    np.testing.assert_allclose(subset.evaluate(x)["gradient"], selected["gradient"], atol=1e-7)
    bounds = [(-12.0, 12.0)] * 2 + [(-5.0, 5.0)] * len(docs)
    fits = []
    for weight in (0.99, 1.01, 0.5):
        weighted = Weighted(model, subset, weight)

        def objective(z, weighted=weighted):
            out = weighted.evaluate(z)
            return -out["score"], -out["gradient"]

        fit = minimize(
            objective,
            x,
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options=dict(maxiter=100, maxfun=160, ftol=1e-14, gtol=1e-6, maxls=25),
        )
        boundary = any(
            min(v - lo, hi - v) < 0.001 for v, (lo, hi) in zip(fit.x, bounds, strict=True)
        )
        differences = []
        for i, step in enumerate([1e-4, 1e-4] + [1e-5] * len(docs)):
            p, m = fit.x.copy(), fit.x.copy()
            p[i] += step
            m[i] -= step
            numerical = (
                weighted.evaluate(p, False)["score"] - weighted.evaluate(m, False)["score"]
            ) / (2 * step)
            differences.append(abs(numerical + fit.jac[i]))
        pg = float(max(abs(fit.jac)))
        scored = model.evaluate(fit.x, gradient=False, held=True)
        selected_keys = {(r["session_id"], r["track_id"]) for r in selected["members"]}
        gains = {"selected": 0.0, "remaining": 0.0}
        for row in scored["rows"]:
            k = row["session_id"], row["track_id"]
            gains["selected" if k in selected_keys else "remaining"] += (
                row["held_log_score"] - lookup[k]["held_log_score"]
            )
        fits.append(
            dict(
                weight=weight,
                x=fit.x.tolist(),
                success=bool(fit.success),
                message=str(fit.message),
                projected_gradient=pg,
                gradient_audit=max(differences),
                boundary=boundary,
                qualified=bool(
                    fit.success and not boundary and pg <= 0.01 and max(differences) <= 0.02
                ),
                estimate_deg=list(model.models[0].coordinates(fit.x[:3])),
                held_gains=gains,
            )
        )
    numerical = (np.array(fits[1]["x"])[:2] - np.array(fits[0]["x"])[:2]) * 1000 / 0.02
    predicted = response(hessian, np.array(selected["gradient"]), 1.0)
    error = float(np.linalg.norm(numerical - predicted))
    relative = error / max(float(np.linalg.norm(predicted)), 1e-20)
    output = dict(
        unit=key,
        cross_scan_groups=sum(len(r["scans"]) >= 2 for r in ranked),
        ranked=ranked,
        fits=fits,
        baseline_estimate_deg=old["estimate_deg"],
        response_audit_error_m=error,
        response_audit_relative=relative,
        response_audit_passed=bool(
            (relative <= 0.05 or error <= 0.5) and all(f["qualified"] for f in fits[:2])
        ),
        gradient_replay_error=replay,
        tracks=sum(len(d["tracks"]) for d in docs),
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / f"{key}.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(
        key,
        selected["number"],
        len(selected["members"]),
        [f["qualified"] for f in fits],
        output["response_audit_passed"],
        output["elapsed_seconds"],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
