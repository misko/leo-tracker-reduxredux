"""Audit every saved regional endpoint in a shared joint-clock model; no fits."""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    InitialClockObjective,
    load_member,
    predict_orbits,
    read,
    transport,
    write_json,
)


def main():
    protocol = read(HERE / "protocol.json")
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first census")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    numbers = protocol["candidate_union"]
    union = case.bank.select([lookup[n] for n in numbers])
    ordinary = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    selected = next(
        a["selected"] for a in ordinary["methods"][0]["arms"] if a["name"] == "fitted-c"
    )

    def model(cal, bank, sigma):
        base = Hard60Objective(
            case.prepared.observations,
            bank,
            case.prior,
            replace(HARD60_SCORE, relative_sigma_s=sigma),
            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
        )
        correction = cal["correction"]
        return base, InitialClockObjective(base, correction["nodes_s"], correction["knots_hz"], 2)

    _, common = model(ordinary["diagnostics"]["calibrations"][selected["source_basin"]], union, 1)
    rows = []
    for region in protocol["complete_regions"]:
        document = read(
            REPORTS / f"2026_10_08_position_error_iter41/results/region-{region:02d}.json"
        )["document"]
        for start in document["diagnostics"]["final_starts"]:
            row = dict(
                region=region, source_arm=start["arm"], start=start["start"], basin=start["basin"]
            )
            if not start["fit"]:
                row.update(status="missing_fit")
                rows.append(row)
                continue
            cal = document["diagnostics"]["calibrations"][start["basin"]]
            bank = case.bank.select(cal["satellite_indices"])
            base, old = model(cal, bank, 2)
            vector = np.asarray(start["fit"]["vector"])
            clock = old.initial_clock.copy()
            np.testing.assert_allclose(
                base.evaluate(vector)[0], start["fit"]["objective"], atol=1e-6, rtol=0
            )
            indices = [numbers.index(int(n)) for n in bank.numbers]
            seed, delta = transport(old, common, vector, clock, indices)
            old_p, old_v, _, _ = predict_orbits(
                bank,
                case.prepared.observations,
                case.prior,
                vector[:2],
                vector[7] + old.basis @ vector[8:],
            )
            new_p, new_v, _, _ = predict_orbits(
                union,
                case.prepared.observations,
                case.prior,
                seed[:2],
                seed[7] + common.basis @ seed[8:],
            )
            np.testing.assert_allclose(new_p[:, indices], old_p, atol=1e-6, rtol=0)
            np.testing.assert_array_equal(new_v[:, indices], old_v)
            limits = dict(
                slope_hz_s=float(max(abs(seed[[3, 5]]))),
                c=float(abs(seed[6])),
                common_s=float(abs(seed[7])),
                total_timing_s=float(max(abs(seed[7] + common.basis @ seed[8:]))),
                clock_hz=float(max(abs(clock))),
            )
            violations = [
                k
                for k, limit in dict(
                    slope_hz_s=60, c=5000, common_s=10, total_timing_s=20, clock_hz=2000
                ).items()
                if limits[k] > limit + 1e-8
            ]
            row.update(
                status="infeasible" if violations else "feasible",
                violations=violations,
                limits=limits,
                source_converged=start["fit"]["converged"],
                seed=seed.tolist(),
                clock=clock.tolist(),
                affine_delta=delta.tolist(),
                common_score=float(common.evaluate_joint(seed, clock)[0]),
            )
            rows.append(row)
        print(region, len(rows), flush=True)
    write_json(
        HERE / "results.json", dict(rows=rows, candidate_union=numbers, scope=protocol["scope"])
    )


if __name__ == "__main__":
    main()
