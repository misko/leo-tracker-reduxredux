"""Fixed-vector normalization versus common-bank audit, no optimization."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from bank_score import score_bank

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import Hard60Objective, HARD60_SCORE, predict_orbits  # noqa: E402
from pipeline import InitialClockObjective  # noqa: E402
from inputs import write_json  # noqa: E402
from newer import load_member  # noqa: E402
# isort: on


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    output = HERE / "results.json"
    if output.exists():
        raise FileExistsError("Preserve first common-bank score audit")
    members = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())[
        "members"
    ]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    numbers = plan["candidate_union"]
    union = case.bank.select([lookup[n] for n in numbers])
    union_lookup = {n: i for i, n in enumerate(numbers)}
    rows = []

    def audit(name, scope, document, fitted, arm, joint=False):
        selected = next(a["selected"] for a in document["methods"][0]["arms"] if a["name"] == arm)
        # Both c arms use the same regional bank and calibration.
        old_numbers = selected["satellites"]
        basin = selected["source_basin"]
        cal = document["diagnostics"]["calibrations"][basin]
        bank = case.bank.select([lookup[n] for n in old_numbers])
        model = Hard60Objective(
            case.prepared.observations,
            bank,
            case.prior,
            HARD60_SCORE,
            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
        )
        vector = np.asarray(fitted["vector"])
        if arm == "zero-c":
            assert vector[6] == 0
        if joint:
            model = InitialClockObjective(
                model, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
            )
            clock = np.asarray(fitted["clock_coefficients"])
            value, _, _, terms = model.evaluate_joint(vector, clock)
            nuisance = model.baseline + model.design @ vector[2:7] + model.clock_design @ clock
            external_penalty = 0
        else:
            value, _, terms = model.evaluate(vector)
            nuisance = model.baseline + model.design @ vector[2:7]
            external_penalty = selected["calibration_penalty"]
        np.testing.assert_allclose(value, fitted["objective"], atol=1e-6, rtol=0)
        relative = model.basis @ vector[8:]
        old_prediction, old_visible, _, _ = predict_orbits(
            bank, model.observations, case.prior, vector[:2], vector[7] + relative
        )
        old_prediction += nuisance[:, None]
        indices = [union_lookup[n] for n in old_numbers]
        all_relative = np.zeros(len(numbers))
        all_relative[indices] = relative
        prediction, visible, _, _ = predict_orbits(
            union, model.observations, case.prior, vector[:2], vector[7] + all_relative
        )
        prediction += nuisance[:, None]
        np.testing.assert_allclose(prediction[:, indices], old_prediction, atol=1e-6, rtol=0)
        np.testing.assert_array_equal(visible[:, indices], old_visible)
        penalty = float(value - terms.nll + external_penalty)
        modes = dict(
            native=score_bank(
                model.observations.measured_hz, old_prediction, old_visible, model.score
            ),
            normalization_only=score_bank(
                model.observations.measured_hz,
                old_prediction,
                old_visible,
                model.score,
                len(numbers),
            ),
            union=score_bank(model.observations.measured_hz, prediction, visible, model.score),
        )
        np.testing.assert_allclose(modes["native"]["nll"], terms.nll, atol=1e-6, rtol=0)
        for result in modes.values():
            result["penalized_score"] = result["nll"] + penalty
        error = fitted.get("error_km", selected["horizontal_error_m"] / 1000)
        rows.append(
            dict(
                name=name,
                scope=scope,
                arm=arm,
                candidate_count=len(old_numbers),
                error_km=error,
                penalty=penalty,
                converged=fitted["converged"],
                modes=modes,
            )
        )

    for index in plan["complete_regions"]:
        data = json.loads(
            (
                REPORTS / "2026_10_08_position_error_iter41/results" / f"region-{index:02d}.json"
            ).read_text()
        )
        document = data["document"]
        for arm in document["methods"][0]["arms"]:
            audit(f"region-{index:02d}", "regional", document, arm["selected"], arm["name"])
    original = json.loads(
        (REPORTS / "2026_10_08_position_error_iter29/results/RESERVED-001.json").read_text()
    )
    baseline = json.loads(
        (REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json").read_text()
    )
    for arm, fitted in original["upstream"]["stages"]["joint-100"].items():
        audit("ordinary-joint", "joint", baseline, fitted, arm, True)
    recovered = json.loads(
        (
            REPORTS / "2026_10_08_position_error_iter40/results/RESERVED-001-recovered.json"
        ).read_text()
    )
    document = json.loads(
        (REPORTS / "2026_10_08_position_error_iter41/results/region-22.json").read_text()
    )["document"]
    for arm, fitted in recovered["upstream"]["stages"]["joint-100"].items():
        audit("recovered-joint", "joint", document, fitted, arm, True)
    write_json(output, dict(rows=rows, candidate_union=numbers))
    print("Audited", len(rows), "saved solutions across three score variants", flush=True)


if __name__ == "__main__":
    main()
