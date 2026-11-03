"""All-track fixed-site failure decomposition and feasibility-aware proposals.

No hardware, orbit phase or geographic parameters are re-fitted. Null controls
hold real-data calibration fixed; they are conditional specificity diagnostics.
"""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from consolidate_shared_phase_matches import consolidate_fit

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.polynomial_satellite_diagnostics import (
    feasible_order,
    orbit_shape_lower_bounds,
)

ROOT = Path(__file__).resolve().parents[1]
PERIOD = 1 / 4.4e-6


def evaluate_all(
    tracks, stats, terms, beta, times, frequency, support, phase_allowed, *, shifts=None
):
    results = []
    for fi, track in enumerate(tracks):
        indexes = np.searchsorted(times, track["times"])
        g, q = matching.group(track), track["rf_hz"] / 11.5e9
        calibration = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
        if len(beta) == 9:
            calibration += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
        observed = track["values"] + (shifts[fi] if shifts is not None else 0) - calibration
        preliminary = (
            stats["component_visible"][fi]
            & (terms.residual_mse[fi] <= 450**2)
            & (np.abs(terms.bias_hz[fi]) <= 3000)
            & phase_allowed
            & support[g]
        )
        candidates = np.flatnonzero(preliminary)
        diagnostics, passed = None, np.array([], int)
        if len(candidates):
            residual = observed[None, :] - q * frequency[candidates][:, indexes]
            residual += terms.aliases[fi, candidates, None] * PERIOD
            residual -= terms.bias_hz[fi, candidates, None]
            passed, diagnostics = feasible_order(
                terms.score[fi], preliminary, residual, track["times"]
            )
        chosen = int(passed[0]) if len(passed) else None
        results.append(
            dict(
                component=track["key"],
                points=len(track["times"]),
                compatible=chosen is not None,
                candidate_index=chosen,
                feasible_candidates=passed.tolist(),
                preliminary_candidates=len(candidates),
                best_preliminary_failed_noise=bool(len(candidates) and not len(passed)),
                rms_hz=None if chosen is None else float(np.sqrt(terms.residual_mse[fi, chosen])),
                bias_hz=None if chosen is None else float(terms.bias_hz[fi, chosen]),
            )
        )
    return results


def analyze(case, variant, fit_root, output):
    original = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
    fit_path = fit_root / case / variant / "diagnosis.json"
    study = json.loads(fit_path.read_text())[0]
    fit, association = study["fit"], study["association"]
    output.mkdir(parents=True, exist_ok=False)
    tracks = load_tracks(original)
    bank_path = Path(f"/tmp/ds22-shared-phase-bank-{case}")
    sky = dict(np.load(bank_path / "bank.npz"))
    receipt = json.loads((bank_path / "receipt.json").read_text())
    assert (
        hashlib.sha256((original / "tracks.json").read_bytes()).hexdigest()
        == receipt["tracks_sha256"]
    )
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    beta, phases = np.asarray(fit["beta"]), np.asarray(fit["phases_s"])
    frequency, elevation = phase_frequency_grid(
        sky, times, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=phases
    )
    stats = matching.statistics(
        [(t["key"], [t]) for t in tracks],
        dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
        {str(t["channel"]): 0.0 for t in tracks},
    )
    terms = profile_component_bias(stats, beta, bias_sigma_hz=1000.0)
    old = {r["component"]: r for r in association["rows"]}
    support = np.zeros(4, bool)
    satellite_support = set()
    for track in tracks:
        row = old[track["key"]]
        if row["compatible"] and row["active_curvature"]:
            support[matching.group(track)] = True
            satellite_support.add(row["candidate_norad"])
    phase_allowed = (np.abs(phases) <= 1e-3) | np.isin(sky["norad"], list(satellite_support))
    proposals = evaluate_all(tracks, stats, terms, beta, times, frequency, support, phase_allowed)
    enriched, details = [], []
    for fi, (track, proposal) in enumerate(zip(tracks, proposals, strict=True)):
        baseline = old[track["key"]]
        j = int(terms.best[fi])
        assert int(sky["norad"][j]) == baseline["candidate_norad"]
        assert abs(terms.rms_hz[fi] - baseline["rms_hz"]) < 1e-5
        assert (j in proposal["feasible_candidates"]) == baseline["compatible"]
        if baseline["compatible"]:
            assert proposal["candidate_index"] == j
        ix = np.searchsorted(times, track["times"])
        g, q = matching.group(track), track["rf_hz"] / 11.5e9
        calibration = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
        if len(beta) == 9:
            calibration += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
        observed = track["values"] - calibration
        shape = orbit_shape_lower_bounds(observed, track["times"], q * frequency[:, ix])
        visible = stats["component_visible"][fi]
        constant_rms = np.where(visible, shape["rms_offset_hz"], np.inf)
        affine_rms = np.where(visible, shape["rms_affine_hz"], np.inf)
        jc, ja = int(np.argmin(constant_rms)), int(np.argmin(affine_rms))
        assert np.isfinite(constant_rms[jc])
        constant_bias = (shape["mean_hz"][jc] + PERIOD / 2) % PERIOD - PERIOD / 2
        reason = (
            "already_accepted"
            if baseline["compatible"]
            else "valid_alternative_rejected_by_ordering"
            if proposal["compatible"]
            else "offset_or_identity_freedom_fits"
            if constant_rms[jc] <= 150
            else "needs_track_specific_slope"
            if affine_rms[ja] <= 150
            else "remaining_curvature_or_measurement_mismatch"
        )
        chosen = proposal["candidate_index"]
        row = dict(
            proposal,
            baseline_compatible=baseline["compatible"],
            active_curvature=baseline["active_curvature"],
            time_span_s=float(np.ptp(track["times"])),
            reason=reason,
            candidate_norad=None if chosen is None else int(sky["norad"][chosen]),
            phase_s=None if chosen is None else float(phases[chosen]),
            candidate_rank=None
            if chosen is None
            else int(np.flatnonzero(np.argsort(terms.score[fi], kind="stable") == chosen)[0]) + 1,
            best_offset_candidate=int(sky["norad"][jc]),
            best_offset_rms_hz=float(constant_rms[jc]),
            best_offset_required_hz=float(constant_bias),
            offset_candidates_below_150=int(np.count_nonzero(constant_rms <= 150)),
            best_affine_candidate=int(sky["norad"][ja]),
            best_affine_rms_hz=float(affine_rms[ja]),
            best_affine_extra_slope_hz_s=float(shape["slope_hz_s"][ja]),
            affine_candidates_below_150=int(np.count_nonzero(affine_rms <= 150)),
        )
        enriched.append(row)
        details.append(
            dict(
                component=track["key"],
                time_s=track["times"],
                observed_native_hz=observed,
                current_prediction_native_hz=q * frequency[j, ix]
                + terms.bias_hz[fi, j]
                - terms.aliases[fi, j] * PERIOD,
                free_offset_prediction_native_hz=q * frequency[jc, ix] + shape["mean_hz"][jc],
                free_affine_residual_hz=observed
                - q * frequency[ja, ix]
                - shape["mean_hz"][ja]
                - shape["slope_hz_s"][ja] * (track["times"] - track["times"].mean()),
            )
        )
    new_association = dict(
        association,
        rows=enriched,
        compatible_points=sum(r["points"] for r in enriched if r["compatible"]),
        compatible_fragments=sum(r["compatible"] for r in enriched),
    )
    write(output / "association.json", new_association)
    write(output / "examples_data.json", details)
    consolidated = consolidate_fit(original, sky, fit, new_association)
    write(output / "consolidated.json", consolidated)
    null = []
    for seed in range(8):
        shifts = np.random.default_rng(271800 + seed).uniform(-PERIOD / 2, PERIOD / 2, len(tracks))
        shifted = dict(stats, mean=stats["mean"] + shifts[:, None])
        values = profile_component_bias(shifted, beta, bias_sigma_hz=1000.0)
        result = evaluate_all(
            tracks, shifted, values, beta, times, frequency, support, phase_allowed, shifts=shifts
        )
        null.append(
            dict(
                seed=271800 + seed,
                compatible_points=sum(r["points"] for r in result if r["compatible"]),
                compatible_fragments=sum(r["compatible"] for r in result),
                unique_points=sum(
                    r["points"] for r in result if len(r["feasible_candidates"]) == 1
                ),
            )
        )
        write(output / "null.json", null)
    reason_counts = {
        reason: dict(
            fragments=sum(r["reason"] == reason for r in enriched),
            points=sum(r["points"] for r in enriched if r["reason"] == reason),
        )
        for reason in sorted({r["reason"] for r in enriched})
    }
    summary = dict(
        case=case,
        variant=variant,
        graph_points=association["points"],
        baseline_points=association["compatible_points"],
        all_feasible_points=new_association["compatible_points"],
        all_feasible_fragments=new_association["compatible_fragments"],
        unique_points=sum(r["points"] for r in enriched if len(r["feasible_candidates"]) == 1),
        unique_fragments=sum(len(r["feasible_candidates"]) == 1 for r in enriched),
        consolidated_tracks=consolidated["output_tracks"],
        baseline_points_lost=0,
        diagnostic_reason_counts=reason_counts,
        null_points=[r["compatible_points"] for r in null],
        fixed_calibration_null_not_full_procedure_fdr=True,
        no_satellite_identity_truth=True,
        no_position_estimate=True,
    )
    write(output / "summary.json", summary)
    write(
        output / "protocol.json",
        dict(
            fit_sha256=hashlib.sha256(fit_path.read_bytes()).hexdigest(),
            bank_receipt=receipt,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            diagnostic_module_sha256=hashlib.sha256(
                ROOT.joinpath(
                    "src/leo/analysis/research/polynomial_satellite_diagnostics.py"
                ).read_bytes()
            ).hexdigest(),
            original_observations_unchanged=True,
            all_candidates_checked=True,
            hardware_and_satellite_phase_frozen=True,
            original_gates_unchanged=True,
            linear_tracks_do_not_calibrate=True,
            original_qualified_calibration_support_frozen=True,
            diagnostic_unpenalized_offset_affine_threshold_hz=150,
            no_fit=True,
            null_seeds=list(range(271800, 271808)),
        ),
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True)
    p.add_argument("--fit-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    for variant in ("c0", "fitted_c"):
        analyze(a.case, variant, a.fit_root, a.output / a.case / variant)
