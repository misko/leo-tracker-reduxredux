import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from model import terms
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def perturbed(docs, di, ti, index, delta):
    changed = list(docs)
    tracks = list(docs[di]["tracks"])
    y = tracks[ti]["y"].copy()
    assert tracks[ti]["mask"][index]
    y[index] += delta
    tracks[ti] = dict(tracks[ti], y=y)
    changed[di] = dict(docs[di], tracks=tracks)
    return changed


def main(key):
    start = time.monotonic()
    plan_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    fit_path = HERE.parent / "2026_09_29_sparse_waveform_position" / f"{key}.json"
    plan, saved = [json.loads(p.read_text()) for p in (plan_path, fit_path)]
    for path, digest in saved["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents(dict(config=plan["config"], inputs=unit["group"]["inputs"]))
    config = plan["config"]
    model = TrendMixturePosition(docs, config, baseline.Stationary, 0.2)
    old = saved["arms"]["cached"]["selected"]
    assert old["audit_passed"]
    x = np.asarray(old["x"])
    control = model.evaluate(x, gradient=True)
    assert abs(control["score"] - old["score"]) < 1e-7
    steps = np.array([0.001, 0.001] + [0.0001] * len(docs))
    matrices = []
    for fraction in (1.0, 0.5):
        columns = []
        for axis, step in enumerate(steps * fraction):
            a, b = x.copy(), x.copy()
            a[axis] += step
            b[axis] -= step
            columns.append(
                -(model.evaluate(a)["gradient"] - model.evaluate(b)["gradient"]) / (2 * step)
            )
        matrices.append(np.array(columns).T)
    raw = matrices[1]
    hessian = (raw + raw.T) / 2
    norm = max(np.linalg.norm(hessian), 1e-30)
    symmetry = float(np.linalg.norm(raw - raw.T) / norm)
    step_error = float(np.linalg.norm(matrices[0] - matrices[1]) / norm)
    eigenvalues = np.linalg.eigvalsh(hessian)
    qualified = bool(min(eigenvalues) > 0 and symmetry <= 0.005 and step_error <= 0.005)
    output = dict(
        unit=key,
        hessian=hessian.tolist(),
        eigenvalues=eigenvalues.tolist(),
        symmetry_error=symmetry,
        step_error=step_error,
        hessian_qualified=qualified,
    )
    if qualified:
        columns = []
        metadata = []
        total_gradient = np.zeros_like(x)
        total_score = 0.0
        for di, (doc, engine) in enumerate(zip(docs, model.models, strict=True)):
            local = np.array([x[0], x[1], x[di + 2]])
            for ti, track in enumerate(doc["tracks"]):
                mask = track["mask"]
                prediction, visible = engine.prediction(track, local)
                derivative = []
                for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
                    a, b = local.copy(), local.copy()
                    a[axis] += step
                    b[axis] -= step
                    pa, va = engine.prediction(track, a)
                    pb, vb = engine.prediction(track, b)
                    assert np.array_equal(visible, va) and np.array_equal(visible, vb)
                    derivative.append((pa[visible][:, mask] - pb[visible][:, mask]) / (2 * step))
                density, g, cross = terms(
                    track["y"][mask],
                    np.asarray(track["times_s"])[mask],
                    prediction[visible][:, mask],
                    np.stack(derivative, axis=2),
                )
                total_score += density
                total_gradient[[0, 1, di + 2]] += g
                full = np.zeros((len(x), int(mask.sum())))
                full[[0, 1, di + 2]] = cross
                columns.append(full)
                for index in np.flatnonzero(mask):
                    metadata.append(
                        dict(
                            session_id=doc["session_id"],
                            track_id=track["track_id"],
                            index=int(index),
                            visit=track["visits"][index],
                            time_s=track["times_s"][index],
                            receiver_id=track["receiver_id"],
                            sample_rate_hz=doc["sample_rate_hz"],
                            di=di,
                            ti=ti,
                        )
                    )
        score_error = abs(total_score - control["score"])
        gradient_error = float(np.max(abs(total_gradient - control["gradient"])))
        assert score_error < 1e-7 and gradient_error < 1e-7
        cross = np.concatenate(columns, axis=1)
        response = np.linalg.solve(hessian, cross)[:2] * 1000
        sensitivity = np.linalg.norm(response, axis=0)
        ranked = np.argsort(-sensitivity, kind="stable")
        eligible = [i for i in ranked if metadata[i]["sample_rate_hz"] >= 5e6]

        def record(i):
            return dict(
                metadata[i],
                sensitivity_m_per_hz=float(sensitivity[i]),
                response_m_per_hz=response[:, i].tolist(),
            )

        earlier = {(r["session_id"], r["track_id"], r["index"]) for r in saved["applied"]}
        old_indices = [
            i
            for i, r in enumerate(metadata)
            if (r["session_id"], r["track_id"], r["index"]) in earlier
        ]
        assert len(old_indices) == 8
        top = eligible[0]
        selected = metadata[top]
        di, ti, index = [selected[n] for n in ("di", "ti", "index")]
        local = np.array([x[0], x[1], x[di + 2]])
        numerical = []
        for delta in (0.1, -0.1):
            changed = perturbed(docs, di, ti, index, delta)
            one = dict(changed[di], tracks=[changed[di]["tracks"][ti]])
            m = TrendMixturePosition([one], config, baseline.Stationary, 0.2)
            numerical.append(m.evaluate(local)["gradient"])
        cross_error = float(
            np.max(abs((numerical[0] - numerical[1]) / 0.2 - cross[[0, 1, di + 2], top]))
        )
        assert cross_error < 1e-5
        fits = []
        for delta in (10.0, -10.0):
            changed = perturbed(docs, di, ti, index, delta)
            m = TrendMixturePosition(changed, config, baseline.Stationary, 0.2)

            def objective(z, m=m):
                out = m.evaluate(z)
                return -out["score"], -out["gradient"]

            fit = minimize(
                objective,
                x,
                jac=True,
                method="L-BFGS-B",
                bounds=[(-12, 12)] * 2 + [(-5, 5)] * len(docs),
                options=dict(maxiter=100, maxfun=160, ftol=1e-14, gtol=1e-6, maxls=25),
            )
            fits.append(
                dict(
                    delta_hz=delta,
                    x=fit.x.tolist(),
                    success=bool(fit.success),
                    max_gradient=float(np.max(abs(fit.jac))),
                    message=str(fit.message),
                )
            )
        measured = (np.array(fits[0]["x"][:2]) - fits[1]["x"][:2]) * 1000 / 20
        absolute_error = float(np.linalg.norm(measured - response[:, top]))
        relative_error = absolute_error / max(float(sensitivity[top]), 1e-30)
        refit_qualified = bool(
            all(f["success"] and f["max_gradient"] <= 0.01 for f in fits)
            and (relative_error <= 0.05 or absolute_error <= 0.005)
        )
        archive = HERE / f"{key}.npz"
        np.savez_compressed(
            archive,
            response_m_per_hz=response,
            sensitivity=sensitivity,
            doc_index=[r["di"] for r in metadata],
            track_index=[r["ti"] for r in metadata],
            observation_index=[r["index"] for r in metadata],
        )
        energy = float(sensitivity @ sensitivity)
        output.update(
            score_replay_error=score_error,
            gradient_replay_error=gradient_error,
            training_observations=len(metadata),
            eligible_observations=len(eligible),
            top_unrestricted=[record(i) for i in ranked[:8]],
            top_eligible=[record(i) for i in eligible[:8]],
            previous=[record(i) for i in old_indices],
            previous_energy_fraction=float(sum(sensitivity[old_indices] ** 2) / energy),
            queue_energy_fraction=float(sum(sensitivity[eligible[:8]] ** 2) / energy),
            queue_previous_overlap=sum(i in old_indices for i in eligible[:8]),
            cross_audit_error=cross_error,
            refits=fits,
            refit_response_m_per_hz=measured.tolist(),
            response_absolute_error=absolute_error,
            response_relative_error=relative_error,
            refit_qualified=refit_qualified,
            archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        )
    files = [plan_path, fit_path, HERE / "run.py", HERE / "model.py", HERE / "PROTOCOL.md"]
    output["hashes"] = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    output["elapsed_seconds"] = time.monotonic() - start
    (HERE / f"{key}.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(key, qualified, output.get("refit_qualified"), output["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
