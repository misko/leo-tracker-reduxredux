"""Matched S01 merge checks with a pooled noise gate and a bounded gap change."""

import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from consolidate_shared_phase_matches import consolidate_fit

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"


def run():
    output = DEEP / "scan1_pooled_merge_check"
    output.mkdir(exist_ok=False)
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01"
    bank_path = Path("/tmp/ds22-shared-phase-bank-DSX01-S01/bank.npz")
    bank = dict(np.load(bank_path))
    summaries, hashes = [], {}
    configs = [("historical", 10, False), ("pooled_10s", 10, True), ("pooled_30s", 30, True)]
    for arm in ("c0", "fitted_c"):
        path = DEEP / "cohort/DSX01-S01" / arm / "diagnosis.json"
        hashes[arm] = hashlib.sha256(path.read_bytes()).hexdigest()
        row = json.loads(path.read_text())[0]
        original = json.loads(
            (
                DEEP / "baseline_consolidated/DSX01-S01" / arm / "supplied_evaluation_site.json"
            ).read_text()
        )
        for label, gap, pooled in configs:
            result = consolidate_fit(
                recording,
                bank,
                row["fit"],
                row["association"],
                max_gap_s=gap,
                check_joined_residual=pooled,
            )
            if label == "historical" and result != original:
                raise ValueError("default implementation no longer reproduces frozen baseline")
            target = {"S01-RX1-CH1-T008", "S01-RX1-CH1-T011"}
            joined = next((g for g in result["groups"] if target <= set(g["members"])), None)
            write(output / f"{arm}_{label}.json", result)
            summaries.append(
                dict(
                    arm=arm,
                    configuration=label,
                    max_gap_s=gap,
                    pooled_screen=pooled,
                    **{
                        k: result[k]
                        for k in (
                            "input_tracks",
                            "output_tracks",
                            "points",
                            "points_dropped",
                            "identities_changed",
                        )
                    },
                    first_continuation_joined=joined is not None,
                    first_continuation_members=None if joined is None else joined["members"],
                    all_final_groups_passed=all(g["residual_check"] for g in result["groups"]),
                    baseline_exactly_reproduced=label == "historical",
                )
            )
    write(output / "summary.json", summaries)
    sources = [
        Path(__file__),
        ROOT / "tools/consolidate_shared_phase_matches.py",
        ROOT / "src/leo/analysis/research/identified_track_merging.py",
    ]
    write(
        output / "protocol.json",
        dict(
            source_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sources
            },
            input_fits_sha256=hashes,
            bank_sha256=hashlib.sha256(bank_path.read_bytes()).hexdigest(),
            original_points_and_identities_preserved=True,
            no_calibration_or_phase_refit=True,
            only_constant_component_bias_is_profiled=True,
            linear_fragments_do_not_calibrate=True,
            c0_and_fitted_c_matched_inputs_candidates_priors_and_configurations=True,
            known_position_frequency_analysis_only=True,
            maximum_gap_change_is_an_experiment_not_an_identity_validation=True,
        ),
    )
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    run()
