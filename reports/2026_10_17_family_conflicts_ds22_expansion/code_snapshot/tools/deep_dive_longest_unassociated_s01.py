"""Full causal candidate/phase audit of S01's longest unassociated polynomial."""

import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import ROOT, load_study

from leo.analysis.research.fixed_assignment_fit import common_candidate_phase_scores
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.robust_polynomial_order import polynomial_orders
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases

OUTPUT = ROOT / "reports/2026_10_17_longest_unassociated_s01"
CURRENT = ROOT / "reports/2026_10_17_cohort_phase_repair/curved_only/association/DSX01-S01"
TARGET = "S01-RX1-CH6-T001"


def run():
    OUTPUT.mkdir(exist_ok=False)
    studies = {}
    locked = set()
    for fitted_c in (False, True):
        arm = "fitted_c" if fitted_c else "c0"
        study, _, _, _, _ = load_study("DSX01-S01", fitted_c)
        fit = json.loads((CURRENT / arm / "fit.json").read_text())
        association = json.loads((CURRENT / arm / "association.json").read_text())["association"]
        locked.update(
            r["candidate_norad"]
            for r in association["rows"]
            if r["compatible"] and r["active_curvature"]
        )
        studies[arm] = study, fit, association
    study = studies["c0"][0]
    track = next(t for t in study.tracks if t["key"] == TARGET)
    assert TARGET in study.curved_keys
    write(OUTPUT / "track.json", track)
    write(
        OUTPUT / "robust_polynomial_orders.json", polynomial_orders(track["times"], track["values"])
    )
    times = track["times"]
    groups = [(TARGET, [track])]
    norads = study.sky["norad"]
    allowed = ~np.isin(norads, list(locked))
    grid = np.linspace(-15, 15, 601)
    results = {
        arm: dict(
            scores=np.zeros((len(grid), len(norads))),
            rms=np.zeros((len(grid), len(norads))),
            bias=np.zeros((len(grid), len(norads))),
            passes=np.zeros((len(grid), len(norads)), bool),
            visible=np.zeros((len(grid), len(norads)), bool),
        )
        for arm in studies
    }

    def score_geometry(phases):
        geometry = prepare_phase_geometry(study.sky, times, phases)
        f, e, h = phase_linear_frequency(
            geometry, studies["c0"][1]["latitude_deg"], studies["c0"][1]["longitude_deg"]
        )
        stats = matching.statistics(
            groups, dict(time_s=times, doppler_0=f, elevation_deg=e), {str(track["channel"]): 0.0}
        )
        stats = recenter_phases(augment_phase_statistics(stats, times, f, h), phases)
        return f, stats

    def evaluate(arm, phases, f, stats):
        experiment, fit, _ = studies[arm]
        beta = np.array(fit["beta"])
        score, terms = common_candidate_phase_scores(stats, beta, phases, experiment.sigma)
        g = matching.group(track)
        hardware = beta[g] + beta[g + 4] * (times - 150) / 150
        if len(beta) == 9:
            hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
        residual = track["values"][None, :] - hardware - track["rf_hz"] / 11.5e9 * f
        residual += terms.aliases[0, :, None] * matching.PERIOD
        residual -= terms.bias_hz[0, :, None]
        noise = batch_noise_screen(residual, times)
        rms = np.sqrt(np.mean(residual**2, axis=1))
        visible = stats["component_visible"][0]
        passes = (
            visible & (rms <= 450) & (np.abs(terms.bias_hz[0]) <= 3000) & noise["noise_screen_pass"]
        )
        return dict(
            scores=score,
            rms=rms,
            bias=terms.bias_hz[0],
            passes=passes,
            visible=visible,
            aliases=terms.aliases[0],
            residual_hz=residual,
            noise=noise,
        )

    frozen = {}
    for arm, (_, fit, _) in studies.items():
        phases = np.array(fit["phases_s"])
        f, stats = score_geometry(phases)
        frozen[arm] = evaluate(arm, phases, f, stats)
    for i, p in enumerate(grid):
        phases = np.full(len(norads), p)
        f, stats = score_geometry(phases)
        for arm in studies:
            values = evaluate(arm, phases, f, stats)
            for field in results[arm]:
                results[arm][field][i] = values[field]
        if (i + 1) % 100 == 0:
            print(
                json.dumps(
                    dict(
                        phases=i + 1,
                        passing_unlocked={
                            arm: int((r["passes"] & allowed).any(axis=0).sum())
                            for arm, r in results.items()
                        },
                    )
                ),
                flush=True,
            )
    for arm, values in results.items():
        folder = OUTPUT / arm
        folder.mkdir()
        fit = studies[arm][1]
        candidate_rows = []
        for j, n in enumerate(norads):
            visible = values["visible"][:, j]
            any_index = int(np.argmin(np.where(visible, values["scores"][:, j], np.inf)))
            shape_index = int(np.argmin(np.where(visible, values["rms"][:, j], np.inf)))
            passes = values["passes"][:, j]
            row = dict(
                norad=int(n),
                ever_visible=bool(visible.any()),
                phase_locked=not bool(allowed[j]),
                old_phase_s=fit["phases_s"][j],
                frozen_rms_hz=float(frozen[arm]["rms"][j]),
                frozen_bias_hz=float(frozen[arm]["bias"][j]),
                frozen_passing=bool(frozen[arm]["passes"][j]),
                best_any=dict(
                    phase_s=float(grid[any_index]),
                    rms_hz=float(values["rms"][any_index, j]),
                    bias_hz=float(values["bias"][any_index, j]),
                    score=float(values["scores"][any_index, j]),
                    passing=bool(passes[any_index]),
                ),
                best_shape=dict(
                    phase_s=float(grid[shape_index]),
                    rms_hz=float(values["rms"][shape_index, j]),
                    bias_hz=float(values["bias"][shape_index, j]),
                    passing=bool(passes[shape_index]),
                ),
            )
            if passes.any():
                k = int(np.argmin(np.where(passes, values["scores"][:, j], np.inf)))
                row["free_phase_passing"] = dict(
                    phase_s=float(grid[k]),
                    rms_hz=float(values["rms"][k, j]),
                    bias_hz=float(values["bias"][k, j]),
                    score=float(values["scores"][k, j]),
                    min_phase_s=float(grid[passes].min()),
                    max_phase_s=float(grid[passes].max()),
                )
            row["admissible_passing"] = bool(
                frozen[arm]["passes"][j] if not allowed[j] else passes.any()
            )
            candidate_rows.append(row)
        candidate_rows.sort(key=lambda r: (not r["ever_visible"], r["best_any"]["score"]))
        write(folder / "candidates.json", candidate_rows)
        np.savez_compressed(
            folder / "phase_grid.npz", phase_s=grid, norad=norads, phase_locked=~allowed, **values
        )
        passing = [r for r in candidate_rows if r["admissible_passing"]]
        free = [r for r in candidate_rows if "free_phase_passing" in r]
        summary = dict(
            arm=arm,
            target=TARGET,
            points=len(times),
            span_s=float(np.ptp(times)),
            candidates=len(norads),
            locked_curved_supported_candidates=sorted(locked),
            admissible_passing=passing,
            free_phase_diagnostic_passing=free,
            top_scored=[r for r in candidate_rows if r["ever_visible"]][:5],
            top_shape=sorted(
                [r for r in candidate_rows if r["ever_visible"]],
                key=lambda r: r["best_shape"]["rms_hz"],
            )[:5],
        )
        write(folder / "summary.json", summary)
        print(
            json.dumps(
                dict(
                    arm=arm,
                    admissible=[r["norad"] for r in passing],
                    free_phase_only=[r["norad"] for r in free],
                    top_shape=summary["top_shape"][:2],
                )
            ),
            flush=True,
        )
    write(
        OUTPUT / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            target=TARGET,
            original_ids=track["observation_ids"],
            original_times_values_rf_unchanged=True,
            all_candidates=study.receipt["bank_sha256"],
            only_curved_track_can_propose_phase=True,
            hardware_frozen=True,
            all_existing_curved_supported_phases_locked_in_admissible_analysis=True,
            all_free_phase_results_are_counterfactual_diagnostics=True,
            phase_grid_s=[-15, 15],
            grid_points=601,
            supplied_position_fixed=True,
            no_geographic_accuracy_claim=True,
            no_final_association_updated=True,
        ),
    )


if __name__ == "__main__":
    run()
