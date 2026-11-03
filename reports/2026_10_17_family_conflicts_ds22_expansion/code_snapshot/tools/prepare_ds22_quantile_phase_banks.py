"""Freeze a predeclared five-scan DS22 pilot with a common phase sensitivity prior."""

import hashlib
import json
import shutil
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from audit_satellite_position_conflicts import OUTPUT, ROOT

from leo.sky.propagation import parse_element_sets

CASES = ["DS22-001", "DS22-034", "DS22-069", "DS22-102", "DS22-137"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    output = OUTPUT / "frozen_inputs"
    output.mkdir(exist_ok=False)
    cohort = json.loads(
        (ROOT / "reports/2026_10_17_ds22_physical_model_revision/cohort.json").read_text()
    )
    manifest = []
    for case in CASES:
        entry = next(r for r in cohort if r["source_id"] == case)
        recording = ROOT / entry["recording_path"]
        source = Path("/tmp") / (
            ("ds22-sealed-orbits-" if case == "DS22-137" else "ds22-merged-orbits-") + case
        )
        receipt = json.loads((source / "receipt.json").read_text())
        assert sha(source / "bank.npz") == receipt["bank_sha256"]
        assert sha(recording / "tracks.json") == receipt["tracks_sha256"]
        assert receipt["candidate_selection_uses_evaluation_position"] is False
        assert all(
            r["element_epoch_utc_ns"] <= receipt["cutoff_utc_ns"]
            and r["collected_utc_ns"] <= receipt["cutoff_utc_ns"]
            for r in receipt["provenance"]
        )
        tracks = load_tracks(recording)
        times = np.concatenate([t["times"] for t in tracks])
        grid = np.arange(np.floor(times.min()) - 17, np.ceil(times.max()) + 18)
        elements = parse_element_sets((source / "selected.tle").read_text())
        p, v, good = matching.ecef_states(elements, receipt["origin_utc_ns"], grid)
        assert good.all()
        with np.load(source / "bank.npz") as old:
            ix = np.searchsorted(grid, old["time_s"])
            assert np.array_equal(grid[ix], old["time_s"])
            assert np.array_equal(old["norad"], elements.satellite_numbers)
            assert np.max(np.abs(p[:, ix] - old["position_km"])) < 1e-9
            assert np.max(np.abs(v[:, ix] - old["velocity_km_s"])) < 1e-9
        folder = output / case
        folder.mkdir()
        np.savez_compressed(
            folder / "bank.npz",
            time_s=grid,
            position_km=p,
            velocity_km_s=v,
            norad=np.array(elements.satellite_numbers),
            phase_sigma_s=np.ones(len(elements)),
            phase_bound_s=np.full(len(elements), 3.0),
        )
        shutil.copyfile(source / "selected.tle", folder / "selected.tle")
        shutil.copyfile(source / "receipt.json", folder / "original_receipt.json")
        phase_receipt = dict(
            receipt,
            original_bank_sha256=receipt["bank_sha256"],
            bank_sha256=sha(folder / "bank.npz"),
            phase_prior=(
                "declared common zero-mean sigma1s bound3s sensitivity, not calibrated covariance"
            ),
            reference_position_used=False,
            latest_tle_sha256=sha(folder / "selected.tle"),
            phase_prior_is_calibrated_covariance=False,
            previous_tle_not_used=True,
        )
        write(folder / "receipt.json", phase_receipt)
        manifest.append(
            dict(
                case=case,
                kind=entry["kind"],
                recording_path=entry["recording_path"],
                original_counts=entry["counts"],
                bank_sha256=phase_receipt["bank_sha256"],
                source_receipt_sha256=sha(folder / "original_receipt.json"),
                phase_receipt_sha256=sha(folder / "receipt.json"),
                original_recording_receipt_sha256=sha(recording / "receipt.json"),
            )
        )
        print(
            json.dumps(
                dict(
                    case=case,
                    candidates=len(elements),
                    raw_points=entry["counts"]["winning_points"],
                )
            ),
            flush=True,
        )
    write(output / "manifest.json", manifest)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            selection=(
                "endpoints, midpoint and adjacent adaptive entries at quartiles; "
                "fixed before search"
            ),
            cases=CASES,
            both_capture_formats_included=True,
            common_phase_sigma_s=1,
            common_phase_bound_s=3,
            declared_prior_is_sensitivity_assumption=True,
            same_population_candidates_priors_and_budgets_in_c_arms=True,
            original_causal_elements_states_and_measurements_preserved=True,
            no_known_position_states_read=True,
        ),
    )


if __name__ == "__main__":
    run()
