"""Cross-evaluate saved fit endpoints and connecting segments, without truth."""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path[:0] = [
    str(REPORTS / n)
    for n in (
        "2026_10_09_position_error_iter61",
        "2026_10_09_position_error_iter58",
        "2026_10_09_position_error_iter52",
    )
]
from common_sigma1 import HARD60_SCORE, Hard60Objective, load_member, read, write_json  # noqa: E402
from native_joint import SmoothJointObjective as Native  # noqa: E402
from smooth_joint import SmoothJointObjective as Numpy  # noqa: E402

from leo.analysis.hard60_bounded_fit import _Problem  # noqa: E402


def main():
    protocol = read(HERE / "protocol.json")
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first endpoint audit")
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in census["candidate_union"]])
    doc = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    selected = next(a["selected"] for a in doc["methods"][0]["arms"] if a["name"] == "fitted-c")
    cal = doc["diagnostics"]["calibrations"][selected["source_basin"]]
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        replace(HARD60_SCORE, relative_sigma_s=1),
        receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
    )
    args = (base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2)
    models = {"numpy": Numpy(*args), "native": Native(*args)}
    rows = []
    for index in (0, 6, 12):
        for arm in ("fitted-c", "zero-c"):
            name = f"{index:03d}-{arm}.json"
            old = read(REPORTS / "2026_10_09_position_error_iter60/results" / name)["fit"]
            new = read(REPORTS / "2026_10_09_position_error_iter62/results" / name)["fit"]
            seed = np.asarray(census["rows"][index]["seed"])
            problem = _Problem(
                models["numpy"],
                seed,
                rf_arm=arm,
                slope_half_width_hz_s=60,
                local_center=seed[:2],
                local_radius_km=25,
            )
            path = []
            for alpha in np.linspace(0, 1, 21):
                vector = (1 - alpha) * np.asarray(old["vector"]) + alpha * np.asarray(new["vector"])
                clock = (1 - alpha) * np.asarray(old["clock_coefficients"]) + alpha * np.asarray(
                    new["clock_coefficients"]
                )
                outcomes = {
                    name: model.evaluate_joint(vector, clock) for name, model in models.items()
                }
                a, b = outcomes["numpy"], outcomes["native"]
                path.append(
                    dict(
                        alpha=float(alpha),
                        numpy_objective=a[0],
                        native_objective=b[0],
                        objective_difference=abs(a[0] - b[0]),
                        parameter_gradient_difference=float(max(abs(a[1] - b[1]))),
                        clock_gradient_difference=float(max(abs(a[2] - b[2]))),
                        feasible=bool(problem.feasible(vector) and max(abs(clock)) <= 2000),
                    )
                )
            np.testing.assert_allclose(
                path[0]["numpy_objective"], old["objective"], atol=1e-7, rtol=0
            )
            np.testing.assert_allclose(
                path[-1]["native_objective"], new["objective"], atol=1e-7, rtol=0
            )
            rows.append(dict(index=index, arm=arm, path=path))
            print(index, arm, max(p["objective_difference"] for p in path), flush=True)
    write_json(HERE / "results.json", dict(rows=rows, scope=protocol["scope"]))


if __name__ == "__main__":
    main()
