"""Audit local gradients and horizon-mask changes at all eight shared-bank outputs."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter46"))
# isort: off
from common_joint import load_member, Hard60Objective, HARD60_SCORE, InitialClockObjective  # noqa: E402
from common_joint import predict_orbits, write_json  # noqa: E402
from joint_clock import _Problem  # noqa: E402
# isort: on


def read(path):
    return json.loads(path.read_text())


def main():
    protocol = read(HERE / "protocol.json")
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first gradient audit")
    source = read(REPORTS / "2026_10_08_position_error_iter46/results.json")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in source["candidate_union"]])
    doc = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    selected = next(a["selected"] for a in doc["methods"][0]["arms"] if a["name"] == "fitted-c")
    cal = doc["diagnostics"]["calibrations"][selected["source_basin"]]
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
    )
    model = InitialClockObjective(
        base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
    )

    def visibility(vector):
        return predict_orbits(
            model.bank,
            model.observations,
            model.prior,
            vector[:2],
            vector[7] + model.basis @ vector[8:],
            derivatives=False,
        )[1]

    outputs = []
    for row in source["rows"]:
        fitted = row["fit"]
        v, clock = np.asarray(fitted["vector"]), np.asarray(fitted["clock_coefficients"])
        value, gradient, clock_gradient, _ = model.evaluate_joint(v, clock)
        np.testing.assert_allclose(value, fitted["objective"], atol=1e-6, rtol=0)
        problem = _Problem(
            model,
            np.asarray(row["transported_seed"]),
            rf_arm=row["arm"],
            slope_half_width_hz_s=60,
            local_center=np.asarray(row["transported_seed"][:2]),
            local_radius_km=25,
        )
        combined = np.r_[v, clock]
        scales = np.r_[problem.scales, np.full(len(clock), 50.0)]
        grad = np.r_[gradient, clock_gradient] * scales
        fixed = np.flatnonzero(problem.lower == problem.upper)
        grad[fixed] = 0
        directions = {}
        for name, index in (
            ("east", 0),
            ("north", 1),
            ("c", 6),
            ("largest_timing", 7 + int(np.argmax(abs(grad[7 : model.size])))),
            ("largest_clock", model.size + int(np.argmax(abs(grad[model.size :])))),
        ):
            if index in fixed:
                continue
            direction = np.zeros(len(combined))
            direction[index] = 1
            directions[name] = direction
        directions["steepest_scaled"] = -grad / max(np.linalg.norm(grad), 1e-30)
        original_visible = visibility(v)
        trials = []
        for name, direction in directions.items():
            analytic = float(grad @ direction)
            for step in protocol["steps"]:
                sides = []
                for sign in (-1, 1):
                    point = combined + sign * step * scales * direction
                    trial_v, trial_clock = point[: model.size], point[model.size :]
                    trial_value = model.evaluate_joint(trial_v, trial_clock)[0]
                    sides.append(
                        dict(
                            sign=sign,
                            delta=float(trial_value - value),
                            feasible=problem.feasible(trial_v)
                            and bool(max(abs(trial_clock)) <= 2000),
                            changed_visible_entries=int(
                                np.sum(visibility(trial_v) != original_visible)
                            ),
                        )
                    )
                trials.append(
                    dict(
                        direction=name,
                        step=step,
                        analytic=analytic,
                        central_difference=(sides[1]["delta"] - sides[0]["delta"]) / (2 * step),
                        sides=sides,
                    )
                )
        output = dict(
            hypothesis=row["hypothesis"],
            source_arm=row["source_arm"],
            arm=row["arm"],
            reported_stationarity=fitted["stationarity"],
            converged=fitted["converged"],
            max_gradient_index=int(np.argmax(abs(grad))),
            max_scaled_gradient=float(max(abs(grad))),
            trials=trials,
        )
        outputs.append(output)
        print(
            row["hypothesis"],
            row["source_arm"],
            row["arm"],
            output["max_gradient_index"],
            output["max_scaled_gradient"],
            flush=True,
        )
    write_json(HERE / "results.json", dict(rows=outputs, scope=protocol["scope"]))


if __name__ == "__main__":
    main()
