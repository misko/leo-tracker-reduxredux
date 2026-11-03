"""Reuse a completed control only after proving the repaired analysis is identical."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from evaluate_shared_satellite_phase import Experiment

ROOT = Path(__file__).resolve().parents[1]


def analysis_input_fingerprint(study):
    """Hash only inputs consumed by calibration, search and final association.

    Polynomial coefficients are deliberately excluded: this physical matcher
    consumes the original measurements, not smoothed polynomial predictions.
    """
    payload = dict(
        bank=study.receipt["bank_sha256"],
        region=study.receipt["regional_center"],
        radius=study.receipt["radius_km"],
        initial=study.initial.tolist(),
        sigma=study.sigma.tolist(),
        bounds=study.bounds.tolist(),
        phase_radius=study.phase_radius_km.tolist(),
        fitted_c=study.fitted_c,
        phase_enabled=study.phase_enabled,
        drift_sigma=study.drift_sigma_hz_s,
        drift_bound=study.drift_bound_hz_s,
        curved_keys=sorted(study.curved_keys),
        calibration_time_s=study.times.tolist(),
        observations=[
            dict(
                key=t["key"],
                receiver=t["receiver"],
                channel=t["channel"],
                rf_hz=t["rf_hz"],
                time_s=np.asarray(t["times"]).tolist(),
                cfo_hz=np.asarray(t["values"]).tolist(),
                ids=t["observation_ids"],
            )
            for t in study.tracks
        ],
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def run(partition, original_output, repaired_output, *, fitted_c):
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/cohort/DS22-001"
    bank = Path("/tmp/ds22-shared-phase-bank-DS22-001")
    controls = [
        Experiment(
            recording,
            bank,
            fitted_c=fitted_c,
            phase_enabled=True,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1.0,
        )
        for _ in range(2)
    ]
    curves = json.loads((partition / "curves.json").read_text())
    for t in curves:
        t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
    background = json.loads((partition / "background.json").read_text())
    receipt = controls[1].set_observation_partition(
        curves, [r["observation_id"] for r in background]
    )
    fingerprints = [analysis_input_fingerprint(s) for s in controls]
    if fingerprints[0] != fingerprints[1] or background:
        raise ValueError("repair changes numerical inputs: a separate search is required")
    # Completion and source validation are required; no stale partial fit reuse.
    required = (
        "fit.json",
        "summary.json",
        "evaluation.json",
        "blind_association.json",
        "fixed_site.json",
        "progress.json",
        "finalists.json",
        "protocol.json",
        "population_protocol.json",
    )
    if any(not (original_output / name).is_file() for name in required):
        raise ValueError("original control has not completed")
    source_protocol = json.loads((original_output / "protocol.json").read_text())
    for filename, digest in source_protocol["source_sha256"].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != digest:
            raise ValueError("original search engine source changed")
    repaired_output.mkdir(parents=True, exist_ok=False)
    copied = {}
    for name in required:
        shutil.copyfile(original_output / name, repaired_output / name)
        copied[name] = hashlib.sha256((original_output / name).read_bytes()).hexdigest()
    summary = json.loads((repaired_output / "summary.json").read_text())
    summary.update(repaired=True, reused_equivalent_control=True)
    write(repaired_output / "summary.json", summary)
    population = json.loads((repaired_output / "population_protocol.json").read_text())
    population.update(repaired=True, partition=receipt, reused_equivalent_control=True)
    write(repaired_output / "population_protocol.json", population)
    write(
        repaired_output / "equivalence_receipt.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            original_output=str(original_output.resolve()),
            original_files_sha256=copied,
            original_input_fingerprint=fingerprints[0],
            repaired_input_fingerprint=fingerprints[1],
            background_observations=0,
            initial_values_curvature_times_and_candidates_identical=True,
            numerical_outputs_reused_without_new_search=True,
            actual_search_budget_is_the_completed_control_budget=True,
            polynomial_metadata_changes_do_not_change_physical_measurements=True,
        ),
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--partition", type=Path, required=True)
    p.add_argument("--original-output", type=Path, required=True)
    p.add_argument("--repaired-output", type=Path, required=True)
    p.add_argument("--fitted-c", action="store_true")
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.repaired_output.resolve(), *a.repaired_output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.partition, a.original_output, a.repaired_output, fitted_c=a.fitted_c)
