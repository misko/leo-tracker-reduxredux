"""Observed curvature and bounded timing profiles around published q020 fits."""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE.parent / "2026_09_29_unassociated_trend"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from geometry import information, profile, relative_difference  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def read(p):
    return json.loads(p.read_text())


def visibility(model, documents, x):
    return [
        m.prediction(t, np.r_[x[:2], x[i + 2]])[1]
        for i, (m, d) in enumerate(zip(model.models, documents, strict=True))
        for t in d["tracks"]
    ]


def main(key):
    plan = read(HERE / "plan.json")
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]})
    assert [d["session_id"] for d in docs] == unit["group"]["session_ids"]
    model = TrendMixturePosition(docs, plan["config"], baseline.Stationary, 0.2)
    x = np.asarray(unit["x"], float)
    old = read(ROOT / unit["baseline_held"])
    center = model.evaluate(x, held=True)
    assert abs(center["score"] - old["training_log_score"]) < 1e-7
    np.testing.assert_allclose(center["gradient"], old["full_training_gradient"], rtol=0, atol=1e-7)
    held_center = sum(r["held_log_score"] for r in center["rows"])
    assert abs(held_center - old["held_log_score"]) < 1e-7
    vis0 = visibility(model, docs, x)

    def gradient(point):
        assert all(
            np.array_equal(a, b) for a, b in zip(vis0, visibility(model, docs, point), strict=True)
        )
        return model.evaluate(point)["gradient"]

    node_distance = np.abs(x[2:] * 4 - np.round(x[2:] * 4)) / 4
    steps = np.r_[[0.002, 0.002], np.minimum(0.0001, node_distance / 2)]
    result = dict(
        unit_id=key,
        center=x.tolist(),
        center_score=center["score"],
        center_held_score=held_center,
        steps=steps.tolist(),
        curvature_qualified=False,
        profiles=[],
    )
    if np.min(steps[2:] / 2) < 1e-5:
        result["curvature_reason"] = "timing_node_too_close"
    else:
        matrices = []
        for step in (steps, steps / 2):
            raw, sym = information(gradient, x, step)
            item = dict(
                raw=raw.tolist(), symmetric=sym.tolist(), asymmetry=relative_difference(raw, raw.T)
            )
            try:
                spatial, response, values, vectors = profile(sym)
                item.update(
                    spatial=spatial.tolist(),
                    response=response.tolist(),
                    eigenvalues=values.tolist(),
                    eigenvectors=vectors.tolist(),
                )
            except ValueError as error:
                item["failure"] = str(error)
            matrices.append(item)
        result["matrices"] = matrices
        if all("spatial" in m for m in matrices):
            change = relative_difference(
                np.asarray(matrices[0]["spatial"]), np.asarray(matrices[1]["spatial"])
            )
            passed = (
                all(m["asymmetry"] <= 0.01 and min(m["eigenvalues"]) > 0 for m in matrices)
                and change <= 0.01
            )
            result.update(
                curvature_qualified=bool(passed),
                profile_relative_change=change,
                curvature_reason="qualified"
                if passed
                else "curvature_tolerance_or_positive_definiteness",
            )
        else:
            result["curvature_reason"] = "nonpositive_timing_information"
        if result["curvature_qualified"]:
            fine = matrices[1]
            response = np.asarray(fine["response"])
            values = np.asarray(fine["eigenvalues"])
            vectors = np.asarray(fine["eigenvectors"])
            result["one_nat_distances_km"] = np.sqrt(2 / values).tolist()
            for axis in (0, 1):
                for radius in (0.25, 1.0):
                    for sign in (-1, 1):
                        offset = sign * radius * vectors[:, axis]
                        point = x[:2] + offset
                        row = dict(
                            axis=axis,
                            radius_km=radius,
                            sign=sign,
                            position=point.tolist(),
                            quadratic_loss=float(0.5 * radius**2 * values[axis]),
                            starts=[],
                            qualified=False,
                        )
                        if np.any(abs(point) > 12):
                            row["reason"] = "position_outside_domain"
                            result["profiles"].append(row)
                            continue

                        def objective(t, point=point):
                            ev = model.evaluate(np.r_[point, t])
                            return -ev["score"], -ev["gradient"][2:]

                        for name, initial in (
                            ("original", x[2:]),
                            ("linear", np.clip(x[2:] + response @ offset, -5, 5)),
                        ):
                            fit = minimize(
                                objective,
                                initial,
                                jac=True,
                                method="L-BFGS-B",
                                bounds=[(-5, 5)] * len(docs),
                                options={
                                    "maxiter": 80,
                                    "maxfun": 120,
                                    "ftol": 1e-14,
                                    "gtol": 1e-8,
                                    "maxls": 30,
                                },
                            )
                            bound = bool(np.any(5 - abs(fit.x) < 0.001))
                            row["starts"].append(
                                dict(
                                    name=name,
                                    initial=initial.tolist(),
                                    timing=fit.x.tolist(),
                                    success=bool(fit.success),
                                    message=str(fit.message),
                                    boundary=bound,
                                    gradient=(-fit.jac).tolist(),
                                    score=-float(fit.fun),
                                    evaluations=int(fit.nfev),
                                    qualified=bool(
                                        fit.success and not bound and max(abs(fit.jac)) <= 0.01
                                    ),
                                )
                            )
                        eligible = [r for r in row["starts"] if r["qualified"]]
                        selected = max(eligible, key=lambda r: r["score"]) if eligible else None
                        row["selected"] = selected
                        if selected:
                            z = np.r_[point, selected["timing"]]
                            ev = model.evaluate(z, held=True)
                            checks = []
                            for index in range(2, len(z)):
                                for step in (0.0000625, 0.00003125):
                                    delta = np.eye(len(z))[index] * step
                                    numerical = (
                                        model.evaluate(z + delta, gradient=False)["score"]
                                        - model.evaluate(z - delta, gradient=False)["score"]
                                    ) / (2 * step)
                                    checks.append(
                                        dict(
                                            axis=index,
                                            step=step,
                                            numerical=numerical,
                                            difference=abs(numerical - ev["gradient"][index]),
                                            crosses_node=bool(
                                                np.floor((z[index] - step) * 4)
                                                != np.floor((z[index] + step) * 4)
                                            ),
                                        )
                                    )
                            agreement = [
                                abs(checks[2 * i]["numerical"] - checks[2 * i + 1]["numerical"])
                                for i in range(len(docs))
                            ]
                            passed = (
                                all(
                                    c["difference"] < 0.002 and not c["crosses_node"]
                                    for c in checks
                                )
                                and max(agreement) < 0.002
                            )
                            row.update(
                                qualified=bool(passed),
                                reason="audited" if passed else "timing_audit_failed",
                                checks=checks,
                                step_agreement=agreement,
                                score=ev["score"],
                                timing_gradient=ev["gradient"][2:].tolist(),
                                training_loss=center["score"] - ev["score"],
                                held_delta=sum(r["held_log_score"] for r in ev["rows"])
                                - held_center,
                                visibility_changed=any(
                                    not np.array_equal(a, b)
                                    for a, b in zip(vis0, visibility(model, docs, z), strict=True)
                                ),
                            )
                            assert abs(ev["score"] - selected["score"]) < 1e-7
                        else:
                            row["reason"] = "no_qualified_timing_start"
                        result["profiles"].append(row)
    with (HERE / "runs" / key / "result.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(
        key,
        result["curvature_reason"],
        sum(p["qualified"] for p in result["profiles"]),
        "profile audits",
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
