"""Bounded saved-vector diagnostic. Importing performs no recording work."""

import hashlib
import json
import os
import runpy
import sys
import time
import types
from pathlib import Path

import numpy as np

from leo.analysis.hard60_score import Hard60Objective, likelihood
from leo.analysis.regional_position_score import ALIAS_HZ

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def states(receipt):
    regions = [v for k, v in receipt["regions"].items() if k.startswith("direct107:")]
    assert len(regions) == 1
    fit = regions[0]["recovery"]["result"]["prefit_qualification"]["fit"]
    chosen = [("base", fit["initial_vector"], fit["initial_objective"])]
    probes = [t for t in fit["trials"] if t["kind"] == "curvature" and t["column"] == 5]
    assert {t["sign"] for t in probes} == {-1, 1}
    chosen += [(f"timing-{t['sign']}", t["vector"], t["objective"]) for t in probes]
    newton = [t for t in fit["trials"] if t["kind"] == "newton"]
    assert [t["damping"] for t in newton] == [1, 0.5, 0.25]
    chosen += [(f"newton-{t['damping']}", t["vector"], t["objective"]) for t in newton]
    assert len(chosen) == 6
    base = np.asarray(chosen[0][1])
    for _, vector, _ in chosen[1:3]:
        change = np.asarray(vector) - base
        assert np.count_nonzero(change) == 1 and change[7] != 0
    return chosen


def decomposition(measured, prediction, visible, score):
    k = prediction.shape[1]
    q = score.detection_budget / k
    residual = (measured[:, None] - prediction + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2
    signal = np.exp(-0.5 * (residual / score.sigma_hz) ** 2) * visible
    signal *= q / (1 - q) / (score.sigma_hz * np.sqrt(2 * np.pi))
    total = score.clutter_rate / ALIAS_HZ + signal.sum(axis=1)
    log_p0 = -score.clutter_rate + visible.sum(axis=1) * np.log1p(-q)
    normalization = -log_p0 + np.log(-np.expm1(log_p0))
    density = -np.log(total)
    return normalization, density


def replay(model, chosen, *, clock=time.monotonic, begun=None, progress=None):
    begun = clock() if begun is None else begun
    rows, full_calls, fixed_calls = [], 0, 0
    progress = {} if progress is None else progress
    progress.update(rows=rows, full_calls=0, fixed_calls=0)
    original = model.evaluate.__func__
    namespace = dict(original.__globals__)
    predictor = namespace["predict_orbits"]
    captured = []

    def capture(*args, **kwargs):
        result = predictor(*args, **kwargs)
        # Production adds receiver terms in place to prediction after returning.
        captured[:] = [(result[0].copy(), *result[1:])]
        return result

    namespace["predict_orbits"] = capture
    evaluate = types.MethodType(types.FunctionType(original.__code__, namespace), model)
    base_visible = None
    base_cells = base_winding = base_row_nll = None
    probes = {}
    base_timing = None
    for name, vector, saved in chosen:
        if clock() - begun >= 120:
            return dict(
                status="budget-exhausted",
                rows=rows,
                full_calls=full_calls,
                fixed_calls=fixed_calls,
                elapsed_s=clock() - begun,
            )
        assert full_calls < 6
        vector = np.asarray(vector, float)
        full_calls += 1
        progress["full_calls"] = full_calls
        value, gradient, terms = evaluate(vector)
        np.testing.assert_allclose(value, saved, atol=1e-6, rtol=0)
        orbit, visible, _, timing = captured[0]
        prediction = orbit + (model.design @ vector[2:7] + model.baseline)[:, None]
        shifts = vector[7] + model.basis @ vector[8:]
        query = model.observations.times_s[:, None] + shifts
        cells = np.minimum(
            np.floor(
                (query - model.bank.nodes_s[0]) / (model.bank.nodes_s[1] - model.bank.nodes_s[0])
            ).astype(int),
            len(model.bank.nodes_s) - 2,
        )
        winding = np.floor(
            (model.observations.measured_hz[:, None] - prediction + ALIAS_HZ / 2) / ALIAS_HZ
        )
        if base_visible is None:
            base_visible, base_cells, base_winding = visible.copy(), cells.copy(), winding.copy()
            base_timing = timing.copy()
        if name.startswith("timing-"):
            probes[name] = dict(
                prediction=prediction.copy(),
                shift=float(vector[7]),
                cells=cells.copy(),
                visible=visible.copy(),
                winding=winding.copy(),
            )
        normalization, density = decomposition(
            model.observations.measured_hz, prediction, visible, model.score
        )
        np.testing.assert_allclose((normalization + density).sum(), terms.nll, atol=1e-9, rtol=0)
        if clock() - begun >= 120:
            return dict(
                status="budget-exhausted",
                rows=rows,
                full_calls=full_calls,
                fixed_calls=fixed_calls,
                elapsed_s=clock() - begun,
            )
        assert fixed_calls < 6
        fixed_calls += 1
        progress["fixed_calls"] = fixed_calls
        fixed = likelihood(model.observations.measured_hz, prediction, base_visible, model.score)
        row_nll = normalization + density
        if base_row_nll is None:
            base_row_nll = row_nll.copy()
        change = row_nll - base_row_nll
        top = np.argsort(-abs(change), kind="stable")[:10]
        rows.append(
            dict(
                name=name,
                vector_sha256=hashlib.sha256(vector.tobytes()).hexdigest(),
                objective=float(value),
                nll=float(terms.nll),
                prior=float(value - terms.nll),
                common_gradient=float(gradient[7]),
                fixed_mask_nll=float(fixed.nll),
                visibility_removed=int(np.sum(base_visible & ~visible)),
                visibility_added=int(np.sum(~base_visible & visible)),
                interpolation_cells_changed=int(np.sum(cells != base_cells)),
                winding_changed=int(np.sum(winding != base_winding)),
                timing_derivative_min=float(timing.min()),
                timing_derivative_max=float(timing.max()),
                normalization_nll=float(normalization.sum()),
                density_nll=float(density.sum()),
                visibility_changed_indices=np.argwhere(visible != base_visible).tolist(),
                interpolation_changed_indices=np.argwhere(cells != base_cells).tolist(),
                winding_changed_indices=np.argwhere(winding != base_winding).tolist(),
                top_absolute_row_nll_change=[
                    dict(index=int(i), delta=float(change[i])) for i in top
                ],
            )
        )
    derivative_audit = None
    if len(probes) == 2:
        plus, minus = probes["timing-1"], probes["timing--1"]
        finite = (plus["prediction"] - minus["prediction"]) / (plus["shift"] - minus["shift"])
        stable = (
            (plus["cells"] == minus["cells"])
            & (plus["cells"] == base_cells)
            & (plus["visible"] == minus["visible"])
            & (plus["visible"] == base_visible)
            & (plus["winding"] == minus["winding"])
            & (plus["winding"] == base_winding)
        )
        derivative_audit = dict(
            stable_components=int(stable.sum()),
            maximum_absolute_error_all=float(np.max(abs(finite - base_timing))),
            maximum_absolute_error_stable=float(np.max(abs(finite[stable] - base_timing[stable])))
            if np.any(stable)
            else None,
        )
    return dict(
        status="complete",
        rows=rows,
        full_calls=full_calls,
        fixed_calls=fixed_calls,
        elapsed_s=clock() - begun,
        prediction_timing_derivative_audit=derivative_audit,
    )


def main():
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(key) == "1"
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    previous = HERE.parent / "2026_10_09_position_error_iter107"
    upstream_path = previous / "protocol.json"
    upstream = json.loads(upstream_path.read_text())
    assert (
        plan["upstream_protocol_sha256"] == hashlib.sha256(upstream_path.read_bytes()).hexdigest()
    )
    assert all(plan["source_sha256"].get(k) == v for k, v in upstream["source_sha256"].items())
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    # Exclusive claim precedes reconstruction: interrupted attempts are never silently retried.
    with (HERE / "attempt.json").open("x") as stream:
        json.dump(dict(protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest()), stream)
    begun = time.monotonic()
    binding = dict(
        protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
        upstream_protocol_sha256=plan["upstream_protocol_sha256"],
        member=plan["member"],
    )
    progress = dict(rows=[], full_calls=0, fixed_calls=0)
    result = dict(status="failed")
    try:
        sys.path.insert(0, str(previous))
        receipt = json.loads((previous / "results/DS17-033/candidate.json").read_text())
        cohort = runpy.run_path(str(previous / "cohort.py"))
        case = cohort["load_member"](plan["member"])
        trigger = receipt["inventory"]["candidates"][0]
        original = trigger["original"]
        model = Hard60Objective(
            case["observations"],
            case["bank"].select(original["bootstrap"]["satellite_indices"]),
            case["prior"],
            cohort["pilot"].core.HARD60_SCORE,
        )
        chosen = states(receipt)
        assert [list(row) for row in chosen] == plan["saved_states"]
        result = replay(model, chosen, begun=begun, progress=progress)
    except Exception as error:
        result.update(progress, status="failed", error=repr(error))
    result.update(binding)
    result["elapsed_s"] = time.monotonic() - begun
    with (HERE / "result.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
