"""Check whether the curved satellite family is collectively noise-like."""

import json

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from deep_dive_longest_unassociated_s01 import OUTPUT
from inventory_clipped_phase_cohort import ROOT


def run():
    tracks = {
        t["key"]: t
        for t in json.loads(
            (
                ROOT
                / "reports/2026_10_17_robust_curve_reassociation/partition/DSX01-S01/curves.json"
            ).read_text()
        )
    }
    for arm in ("c0", "fitted_c"):
        folder = OUTPUT / arm / "curved_consensus"
        states = json.loads((folder / "phase_profile.json").read_text())
        pooled = []
        for state in states:
            rows = [r for r in state["rows"] if r["passing"]]
            if len(rows) != 3:
                continue
            times = np.concatenate([tracks[r["component"]]["times"] for r in rows])
            residual = np.concatenate([r["residual_hz"] for r in rows])
            order = np.argsort(times, kind="stable")
            pooled.append(
                dict(
                    phase_s=state["phase_s"],
                    points=len(residual),
                    rms_hz=float(np.sqrt(np.mean(residual**2))),
                    diagnostics=matching.noise_screen(residual[order], times[order]),
                )
            )
        write(
            folder / "pooled_family_diagnostic.json",
            dict(
                states=pooled,
                pooled_independent_white_noise_screen_passes=any(
                    r["diagnostics"]["noise_screen_pass"] for r in pooled
                ),
                associations_are_per_fragment_and_not_one_forced_merged_family=True,
                remaining_correlation_requires_investigation=True,
            ),
        )
        if arm != "fitted_c":
            continue
        state = next(s for s in states if abs(s["phase_s"] + 2.75) < 1e-8)
        rows = [r for r in state["rows"] if r["passing"]]
        times = np.concatenate([tracks[r["component"]]["times"] for r in rows])
        residual = np.concatenate([r["residual_hz"] for r in rows])
        q = np.concatenate(
            [np.full(r["points"], tracks[r["component"]]["rf_hz"] / 11.5e9) for r in rows]
        )
        ci = np.concatenate([np.full(r["points"], i) for i, r in enumerate(rows)])
        x = (times - times.mean()) / (np.ptp(times) / 2)
        diagnostics = []
        baseline_rss = None
        for degree in range(5):
            design = np.c_[np.polynomial.polynomial.polyvander(x, degree), ci == 1, ci == 2]
            coefficient = np.linalg.lstsq(design, residual / q, rcond=None)[0]
            corrected = residual - q * (design @ coefficient)
            if degree == 0:
                baseline_rss = float(np.sum(corrected**2))
            order = np.argsort(times, kind="stable")
            diagnostics.append(
                dict(
                    degree=degree,
                    extra_shared_shape_parameters=degree,
                    rms_hz=float(np.sqrt(np.mean(corrected**2))),
                    diagnostics=matching.noise_screen(corrected[order], times[order]),
                    bic_improvement_relative_to_physical=float(
                        len(times) * np.log(baseline_rss / np.sum(corrected**2))
                        - degree * np.log(len(times))
                    ),
                )
            )
        write(
            OUTPUT / "pooled_shared_shape_diagnostic.json",
            dict(
                phase_s=-2.75,
                points=len(times),
                rows=diagnostics,
                free_shared_shape_is_diagnostic_only_not_adopted_for_calibration=True,
                all_original_points_kept=True,
                no_geographic_accuracy_claim=True,
            ),
        )


if __name__ == "__main__":
    run()
