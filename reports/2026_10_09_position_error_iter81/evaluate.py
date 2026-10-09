"""Fixed gradient audit and one matched complete-state restart per selected state."""

import hashlib
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
ROOT = REPORTS.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter68"))
from audit import make_model  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import fit, json_value, load_member, read, write_json  # noqa: E402
from joint_clock import _parameterization, _Problem, predict_orbits  # noqa: E402


def diagnose(model, saved, steps):
    vector = np.asarray(saved["fit"]["vector"])
    clock = np.asarray(saved["fit"]["clock_coefficients"])
    problem = _Problem(
        model,
        vector,
        rf_arm=saved["arm"],
        slope_half_width_hz_s=60,
        local_center=vector[:2],
        local_radius_km=25,
    )
    initial, _, _, matrix, constant = _parameterization(problem)
    n = len(initial)
    z = np.r_[initial, clock / 50]

    def evaluate(point):
        v, c = constant + matrix @ point[:n], point[n:] * 50
        value, g, cg, _ = model.evaluate_joint(v, c)
        _, visible, _, _ = predict_orbits(
            model.bank, model.observations, model.prior, v[:2], v[7] + model.basis @ v[8:]
        )
        return value, np.r_[matrix.T @ g, 50 * cg], visible, problem.feasible(v)

    value, gradient, visible, feasible = evaluate(z)
    np.testing.assert_allclose(value, saved["fit"]["objective"], rtol=0, atol=1e-6)
    rows = []
    for label, index in (
        ("largest-core", int(np.argmax(abs(gradient[:n])))),
        ("largest-clock", n + int(np.argmax(abs(gradient[n:])))),
    ):
        for step in steps:
            delta = np.zeros(len(z))
            delta[index] = step
            plus, minus = evaluate(z + delta), evaluate(z - delta)
            rows.append(
                dict(
                    component=label,
                    index=index,
                    step=step,
                    analytic=float(gradient[index]),
                    finite_difference=float((plus[0] - minus[0]) / (2 * step)),
                    plus_delta=float(plus[0] - value),
                    minus_delta=float(minus[0] - value),
                    visibility_changes_plus=int(np.count_nonzero(plus[2] != visible)),
                    visibility_changes_minus=int(np.count_nonzero(minus[2] != visible)),
                    plus_feasible=bool(plus[3]),
                    minus_feasible=bool(minus[3]),
                )
            )
    return dict(objective=float(value), feasible=bool(feasible), differences=rows)


def main():
    plan = read(HERE / "protocol.json")
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert not (HERE / "results.json").exists(), "Preserve executed diagnostic"
    case = load_member(
        next(
            m
            for m in read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
            if m["label"] == "RESERVED-001"
        )
    )
    document = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    model = make_model(case, document, 1, census["candidate_union"])
    output = []
    for path in plan["selected_paths"]:
        saved = read(ROOT / path)
        diagnostics = diagnose(model, saved, plan["difference_steps"])
        prefix = f"{saved['index']:03d}-{saved['order']:02d}-{saved['arm']}"
        write_json(HERE / "diagnostics" / f"{prefix}.json", json_value(diagnostics))
        for arm in ("fitted-c", "zero-c"):
            model.initial_clock = np.asarray(saved["fit"]["clock_coefficients"]).copy()
            result = json_value(
                fit(
                    model,
                    np.asarray(saved["fit"]["vector"]).copy(),
                    arm=arm,
                    maximum_seconds=90,
                    maximum_iterations=600,
                )
            )
            if arm == "zero-c":
                assert result["vector"][6] == 0
            row = dict(source=path, arm=arm, fit=result)
            write_json(HERE / "retries" / f"{prefix}-{arm}.json", row)
            output.append(row)
            print(prefix, arm, result["converged"], result["objective"], flush=True)
    write_json(HERE / "results.json", dict(rows=output))


if __name__ == "__main__":
    main()
