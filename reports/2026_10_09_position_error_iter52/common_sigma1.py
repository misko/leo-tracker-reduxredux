"""Matched common-bank refit with relative timing sigma1 instead of sigma2."""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import Hard60Objective, HARD60_SCORE, predict_orbits  # noqa: E402
from pipeline import InitialClockObjective  # noqa: E402
from joint_clock import fit  # noqa: E402
from inputs import write_json, json_value  # noqa: E402
from newer import load_member  # noqa: E402
from probe import error_km  # noqa: E402
# isort: on


def read(path):
    return json.loads(path.read_text())


def transport(old, common, vector, clock, indices):
    """Preserve physical nuisance prediction and pad relative timing with zeros."""
    delta, *_ = np.linalg.lstsq(common.design[:, :4], old.baseline - common.baseline, rcond=None)
    np.testing.assert_allclose(
        common.design[:, :4] @ delta, old.baseline - common.baseline, atol=1e-7, rtol=0
    )
    np.testing.assert_allclose(old.clock_design, common.clock_design, atol=1e-10, rtol=0)
    relative = np.zeros(len(common.bank.numbers))
    relative[indices] = old.basis @ vector[8:]
    seed = np.r_[vector[:8], common.basis.T @ relative]
    seed[2:6] += delta
    np.testing.assert_allclose(common.basis @ seed[8:], relative, atol=1e-9, rtol=0)
    old_nuisance = old.baseline + old.design @ vector[2:7] + old.clock_design @ clock
    new_nuisance = common.baseline + common.design @ seed[2:7] + common.clock_design @ clock
    np.testing.assert_allclose(new_nuisance, old_nuisance, atol=1e-7, rtol=0)
    return seed, delta


def main():
    plan = read(HERE / "protocol.json")
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first common-bank refit")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    numbers = plan["candidate_union"]
    union = case.bank.select([lookup[n] for n in numbers])
    ordinary_doc = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    recovered_doc = read(REPORTS / "2026_10_08_position_error_iter41/results/region-22.json")[
        "document"
    ]
    ordinary = read(REPORTS / "2026_10_08_position_error_iter29/results/RESERVED-001.json")
    recovered = read(
        REPORTS / "2026_10_08_position_error_iter40/results/RESERVED-001-recovered.json"
    )

    def model(doc, bank=None, relative_sigma=2):
        selected = next(a["selected"] for a in doc["methods"][0]["arms"] if a["name"] == "fitted-c")
        cal = doc["diagnostics"]["calibrations"][selected["source_basin"]]
        selected_bank = (
            bank
            if bank is not None
            else case.bank.select([lookup[n] for n in selected["satellites"]])
        )
        base = Hard60Objective(
            case.prepared.observations,
            selected_bank,
            case.prior,
            replace(HARD60_SCORE, relative_sigma_s=relative_sigma),
            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
        )
        return InitialClockObjective(
            base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
        )

    common = model(ordinary_doc, union, relative_sigma=1)
    fixed = read(REPORTS / "2026_10_08_position_error_iter42/results.json")["rows"]
    rows = []
    for name, document, result in (
        ("ordinary", ordinary_doc, ordinary),
        ("recovered", recovered_doc, recovered),
    ):
        old = model(document)
        indices = [numbers.index(int(n)) for n in old.bank.numbers]
        for source_arm, start in result["upstream"]["stages"]["joint-100"].items():
            vector, clock = np.asarray(start["vector"]), np.asarray(start["clock_coefficients"])
            np.testing.assert_allclose(
                old.evaluate_joint(vector, clock)[0], start["objective"], atol=1e-6, rtol=0
            )
            seed, delta = transport(old, common, vector, clock, indices)
            value = common.evaluate_joint(seed, clock)[0]
            prior_audit = next(
                r for r in fixed if r["name"] == name + "-joint" and r["arm"] == source_arm
            )
            np.testing.assert_allclose(
                value,
                prior_audit["modes"]["union"]["penalized_score"] + 0.375 * np.sum(seed[8:] ** 2),
                atol=1e-6,
                rtol=0,
            )
            old_prediction, old_visible, _, _ = predict_orbits(
                old.bank,
                old.observations,
                old.prior,
                vector[:2],
                vector[7] + old.basis @ vector[8:],
            )
            new_prediction, new_visible, _, _ = predict_orbits(
                common.bank,
                common.observations,
                common.prior,
                seed[:2],
                seed[7] + common.basis @ seed[8:],
            )
            np.testing.assert_allclose(
                new_prediction[:, indices], old_prediction, atol=1e-6, rtol=0
            )
            np.testing.assert_array_equal(new_visible[:, indices], old_visible)
            feasible = bool(
                max(abs(seed[[3, 5]])) <= 60
                and abs(seed[6]) <= 5000
                and abs(seed[7]) <= 10
                and max(abs(seed[7] + common.basis @ seed[8:])) <= 20
                and max(abs(clock)) <= 2000
            )
            for arm in ("fitted-c", "zero-c"):
                row = dict(
                    hypothesis=name,
                    source_arm=source_arm,
                    arm=arm,
                    transported_seed=seed.tolist(),
                    affine_coordinate_delta=delta.tolist(),
                    seed_common_score=value,
                    seed_feasible=feasible,
                )
                if feasible:
                    common.initial_clock = clock.copy()
                    fitted = json_value(
                        fit(common, seed, arm=arm, maximum_seconds=20, maximum_iterations=600)
                    )
                    fitted["error_km"] = error_km(case.prior, fitted["vector"], ordinary_doc)
                    if arm == "zero-c":
                        assert fitted["vector"][6] == 0
                    row["fit"] = fitted
                    print(
                        name, source_arm, arm, fitted["converged"], fitted["error_km"], flush=True
                    )
                else:
                    row["fit"] = None
                    print(name, source_arm, arm, "infeasible transport", flush=True)
                rows.append(row)
                write_json(HERE / "progress.json", dict(rows=rows))
    write_json(HERE / "results.json", dict(rows=rows, candidate_union=numbers, scope=plan["scope"]))


if __name__ == "__main__":
    main()
