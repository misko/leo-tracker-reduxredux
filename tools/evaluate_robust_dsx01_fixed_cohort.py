"""Complete repaired fixed-GPS DSX01 coverage with explicit unchanged-input reuse."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from consolidate_shared_phase_matches import consolidate_tracks
from evaluate_shared_satellite_phase import Experiment
from reuse_equivalent_curve_search import analysis_input_fingerprint

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_robust_curve_reassociation"
BASE = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive/cohort"


def run(case):
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
    partition = REPORT / "partition" / case
    bank = Path("/tmp") / f"ds22-shared-phase-bank-{case}"
    receipt = json.loads((partition / "receipt.json").read_text())
    cores = json.loads((partition / "curves.json").read_text())
    for t in cores:
        t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
    background = json.loads((partition / "background.json").read_text())
    source_tracks = load_tracks(recording)
    source_map = {t["key"]: t for t in source_tracks}
    core_map = {t["key"]: t for t in cores}
    for fitted_c in (False, True):
        arm = "fitted_c" if fitted_c else "c0"
        output = REPORT / "fixed_cohort" / case / arm
        output.mkdir(parents=True, exist_ok=False)
        original = Experiment(
            recording,
            bank,
            fitted_c=fitted_c,
            phase_enabled=True,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1,
        )
        repaired = Experiment(
            recording,
            bank,
            fitted_c=fitted_c,
            phase_enabled=True,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1,
        )
        if original.receipt["tracks_sha256"] != receipt["original_tracks_sha256"]:
            raise ValueError("partition does not bind source observations")
        for name in ("curves", "background"):
            if (
                hashlib.sha256((partition / f"{name}.json").read_bytes()).hexdigest()
                != receipt[f"{name}_sha256"]
            ):
                raise ValueError("partition payload changed")
        bound = repaired.set_observation_partition(cores, [r["observation_id"] for r in background])
        fingerprints = [analysis_input_fingerprint(x) for x in (original, repaired)]
        prior_path = BASE / case / arm / "diagnosis.json"
        prior = json.loads(prior_path.read_text())[0]
        # Validate the old result against current geometry before any reuse.
        rechecked = original.associate(prior["fit"])
        for now, old in zip(rechecked["rows"], prior["association"]["rows"], strict=True):
            if (
                now["component"] != old["component"]
                or now["candidate_norad"] != old["candidate_norad"]
                or now["compatible"] != old["compatible"]
                or abs(now["rms_hz"] - old["rms_hz"]) > 1e-5
            ):
                raise ValueError("frozen baseline cannot be reproduced")
        reused = fingerprints[0] == fingerprints[1]
        if reused:
            fit = prior["fit"]
            association = repaired.associate(fit)
        else:
            # Supplied GPS is intentionally used here: this is not localization.
            fit = repaired.fit(37.849061591561885, -122.48574968092912, 32, exact=True)
            association = repaired.associate(fit)
        before = {
            oid: row["candidate_norad"]
            for row in prior["association"]["rows"]
            if row["compatible"]
            for oid in source_map[row["component"]]["observation_ids"]
        }
        after = {
            oid: row["candidate_norad"]
            for row in association["rows"]
            if row["compatible"]
            for oid in core_map[row["component"]]["observation_ids"]
        }
        if set(after) & {r["observation_id"] for r in background}:
            raise ValueError("background observation entered an association")
        merged = consolidate_tracks(
            cores, repaired.sky, fit, association, max_gap_s=30, check_joined_residual=True
        )
        write(output / "fit.json", fit)
        write(output / "association.json", association)
        write(output / "consolidated.json", merged)
        summary = dict(
            case=case,
            arm=arm,
            original_points=bound["original_points"],
            background_points=bound["background_points"],
            baseline_associated_points=len(before),
            repaired_associated_points=len(after),
            gained_points=len(after.keys() - before.keys()),
            lost_points=len(before.keys() - after.keys()),
            relabelled_points=sum(
                before[oid] != after[oid] for oid in before.keys() & after.keys()
            ),
            merged_tracks=merged["output_tracks"],
            points_per_track=len(after) / max(1, merged["output_tracks"]),
            reused_input_equivalent_fit=reused,
        )
        write(output / "summary.json", summary)
        write(
            output / "protocol.json",
            dict(
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                original_input_fingerprint=fingerprints[0],
                repaired_input_fingerprint=fingerprints[1],
                baseline_sha256=hashlib.sha256(prior_path.read_bytes()).hexdigest(),
                baseline_associations_reproduced=True,
                partition=bound,
                supplied_position_fixed=True,
                not_a_position_accuracy_claim=True,
                reused_fit_only_if_all_analysis_inputs_identical=True,
                no_linear_or_background_calibration=True,
                c0_and_fitted_c_same_observations_candidates_priors_and_seed_budget=True,
                seed_budget=32,
                drift_bound_hz_s=1,
                drift_sigma_hz_s=0.5,
            ),
        )
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=tuple(f"DSX01-S{i:02}" for i in range(2, 6)), required=True)
    run(p.parse_args().case)
