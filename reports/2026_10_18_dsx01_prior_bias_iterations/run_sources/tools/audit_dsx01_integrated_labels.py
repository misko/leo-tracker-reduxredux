"""Replay every label-update attempt and verify score-only acceptance ledgers."""

import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_robust_joint import RobustJoint
from iterate_dsx01_integrated_labels import OUTPUT
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_structured_joint import problem_for
from run_dsx01_clock_transfer import measurement_path


def run():
    checks, ledgers, anchor_checks = [], [], []
    for case in (f"DSX01-S0{k}" for k in range(1, 6)):
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        protocol = json.loads((OUTPUT / case / "protocol.json").read_text())
        incumbent = json.loads(Path(protocol["source"]).read_text())["fits"]
        for record in json.loads((OUTPUT / case / "rounds.json").read_text()):
            for name, candidate in record["ranked"].items():
                p = RobustJoint(
                    scan,
                    candidate["seed"],
                    False,
                    variant="robust",
                    sigma=incumbent["c0"]["diagnostics"]["noise_sigma_hz"],
                    aliases=candidate["aliases"],
                )
                z = p.residual(np.array(incumbent["c0"]["east_north_km"]))
                error = abs(float(z @ z) - candidate["full_c0_anchor_cost"])
                assert error < 1e-5
                anchor_checks.append(
                    dict(case=case, iteration=record["iteration"], name=name, error=error)
                )
            if record["ranked"]:
                assert record["selected_candidate"] == min(
                    record["ranked"], key=lambda k: record["ranked"][k]["full_c0_anchor_cost"]
                )
            candidate = record["attempted_fits"]
            gain = incumbent["c0"]["score"] - candidate["c0"]["score"] if candidate else 0.0
            accepted = bool(candidate and gain >= 1.0)
            assert record["selected_fits"] == (candidate if accepted else incumbent)
            assert abs(record["objective_improvement"] - (gain if accepted else 0)) < 1e-8
            incumbent = record["selected_fits"]
            for group in protocol["curved_groups"]:
                assert len({incumbent["c0"]["rows"][k]["candidate_index"] for k in group}) == 1
            ledgers.append(
                dict(case=case, iteration=record["iteration"], accepted=accepted, gain=gain)
            )
        for path in sorted((OUTPUT / "msteps").glob(f"*/{case}/robust/rounds.json")):
            for record in json.loads(path.read_text()):
                pair = record["fits"]
                assert pair["c0"]["rows"] == pair["fitted_c"]["rows"]
                assert pair["c0"]["aliases"] == pair["fitted_c"]["aliases"]
                assert pair["c0"]["starts"] == pair["fitted_c"]["starts"]
                for arm, fit in pair.items():
                    p = problem_for(scan, fit, "identity")
                    z = p.residual(np.array(fit["parameters"]))
                    error = abs(float(z @ z) - fit["frequency_prior_score"])
                    assert error < 1e-5
                    checks.append(
                        dict(
                            case=case,
                            path=str(path),
                            iteration=record["iteration"],
                            arm=arm,
                            error=error,
                        )
                    )
    result = dict(
        fit_records=len(checks),
        matched_c_pairs=len(checks) // 2,
        checks=checks,
        selection_ledgers=ledgers,
        anchor_cost_checks=anchor_checks,
        all_passed=True,
    )
    write(OUTPUT / "attempt_replay.json", result)
    print(
        json.dumps(dict(records=len(checks), accepted_updates=sum(r["accepted"] for r in ledgers))),
        flush=True,
    )


if __name__ == "__main__":
    run()
