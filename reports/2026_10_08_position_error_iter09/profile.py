"""Oracle score decomposition; reference positions never enter operational inference."""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import root

HERE = Path(__file__).resolve().parent
for directory in (
    HERE.parent / "2026_10_08_position_error_iter01",
    HERE.parent / "2026_10_08_hard60_bounded_recovery",
):
    sys.path.insert(0, str(directory))
from inputs import json_value, write_json  # noqa: E402
from probe import error_km, load  # noqa: E402
from profile_fit import JointClockObjective, fit  # noqa: E402

from leo.analysis.hard60_score import ALIAS_HZ, predict_orbits  # noqa: E402
from leo.analysis.regional_position_score import coordinates  # noqa: E402


def reference_point(prior, lat, lon, start):
    result = root(lambda xy: np.asarray(coordinates(prior, xy)) - [lat, lon], start)
    assert result.success and np.max(abs(result.fun)) < 1e-8
    assert np.linalg.norm(result.x) < prior.radius_km
    return result.x


def decompose(model, row, groups):
    vector, clock = np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
    value, _, _, terms = model.evaluate_joint(vector, clock)
    relative = model.basis @ vector[8:]
    _, visible, _, _ = predict_orbits(
        model.bank,
        model.observations,
        model.prior,
        vector[:2],
        vector[7] + relative,
        derivatives=False,
    )
    q = model.score.detection_budget / len(model.bank.numbers)
    logp0 = -model.score.clutter_rate + visible.sum(axis=1) * np.log1p(-q)
    nll = -(
        logp0
        - np.log(-np.expm1(logp0))
        + np.log(model.score.clutter_rate / ALIAS_HZ / terms.clutter_probability)
    )
    common = 0.5 * (vector[7] / model.score.common_sigma_s) ** 2
    timing = 0.5 * np.sum((relative / model.score.relative_sigma_s) ** 2)
    clock_penalty = 0.5 * clock @ model.precision @ clock
    np.testing.assert_allclose(nll.sum(), terms.nll, atol=1e-7, rtol=0)
    np.testing.assert_allclose(
        nll.sum() + common + timing + clock_penalty, value, atol=1e-7, rtol=0
    )
    return dict(
        data_nll=float(terms.nll),
        common_penalty=float(common),
        relative_penalty=float(timing),
        clock_penalty=float(clock_penalty),
        total=float(value),
        grouped_nll={str(g): float(nll[groups == g].sum()) for g in np.unique(groups)},
        relative_shifts_s=relative.tolist(),
        common_shift_s=float(vector[7]),
    )


def run(label):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    case, document, base, original_seed = load(label)
    previous = json.loads(
        (HERE.parent / "2026_10_08_position_error_iter04/probes" / f"{label}.json").read_text()
    )
    chosen = next(
        r for r in previous["candidates"] if r["variant"] == "joint-wide" and r["arm"] == "fitted-c"
    )
    assert chosen["converged"]
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    model = JointClockObjective(base, correction["nodes_s"], correction["knots_hz"], 2)
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    truth = reference_point(
        case.prior,
        document["reference_latitude_deg"],
        document["reference_longitude_deg"],
        seed[:2],
    )
    terms = model.evaluate_joint(seed, clock)[3]
    groups = model.bank.numbers[np.argmax(terms.responsibilities, axis=1)].copy()
    groups[terms.responsibilities.max(axis=1) < 0.5] = 0
    rows = []
    for arm in ("fitted-c", "zero-c"):
        for name, point, warm in (
            ("selected-fixed", seed[:2], True),
            ("reference-warm", truth, True),
            ("reference-cold", truth, False),
        ):
            start = seed.copy() if warm else original_seed.copy()
            start[:2] = point
            row = fit(
                model, start, arm=arm, fixed_position=True, clock_seed=clock if warm else None
            )
            row.update(arm=arm, phase=name, error_km=error_km(case.prior, row["vector"], document))
            row["decomposition"] = decompose(model, row, groups)
            rows.append(row)
            print(label, arm, name, row["converged"], round(row["objective"], 3), flush=True)
        reference_rows = [
            r
            for r in rows
            if r["arm"] == arm and r["phase"].startswith("reference-") and r["converged"]
        ]
        if reference_rows:
            best = min(reference_rows, key=lambda r: r["objective"])
            row = fit(model, best["vector"], arm=arm, clock_seed=best["clock_coefficients"])
            row.update(
                arm=arm,
                phase="reference-released",
                error_km=error_km(case.prior, row["vector"], document),
            )
            row["decomposition"] = decompose(model, row, groups)
            rows.append(row)
            print(label, arm, "released", row["converged"], round(row["error_km"], 4), flush=True)
    write_json(
        output,
        json_value(
            dict(
                label=label,
                session_id=document["session_id"],
                reference_point_km=truth,
                fitted_selected=chosen,
                satellites=model.bank.numbers.tolist(),
                group_counts={str(g): int((groups == g).sum()) for g in np.unique(groups)},
                rows=rows,
                reference_use="Oracle diagnostic only; not operational initialization or position estimate",
            )
        ),
    )


if __name__ == "__main__":
    for label in sys.argv[1:]:
        assert label in ("S11", "S16", "S24", "S44")
        run(label)
