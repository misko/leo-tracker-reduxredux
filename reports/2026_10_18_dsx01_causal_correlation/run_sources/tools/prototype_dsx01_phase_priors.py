"""Blind causal phase-scale controls with Gaussian and heavy-tailed priors."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_dsx01_continuous_position import CENTER, GRID

OUTPUT = ROOT / "reports/2026_10_18_dsx01_causal_phase_priors"
NOMINATIONS = ROOT / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32"
MODES = ("floor1", "causal_gaussian", "causal_student", "causal_3x")


class CausalPhaseFamilies(AnchoredFamilies):
    def __init__(self, scan, seed, method, fitted_c, anchor, *, mode="causal_gaussian"):
        if mode not in MODES:
            raise ValueError("unknown causal phase prior")
        super().__init__(scan, seed, method, fitted_c, anchor)
        self.mode = mode
        self.phase_sigma = np.maximum(0.1, scan.sky["phase_sigma_s"][self.labels])
        if mode == "floor1":
            self.phase_sigma = scan.sigma[self.labels]
        if mode == "causal_3x":
            self.phase_sigma = 3 * self.phase_sigma
        extra = sum(1 if method == "family_rate" else 2 for _ in self.extra_labels)
        smooth = self.starts["smooth"].size if method == "receiver_smooth" else 0
        length = len(super().residual(self.initial))
        start = length - len(self.labels) - extra - smooth
        self.phase_slice = slice(start, start + len(self.labels))

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        r, diagnostics = result if details else (result, None)
        normalized = r[self.phase_slice] * self.scan.sigma[self.labels] / self.phase_sigma
        if self.mode == "causal_student":
            energy = normalized**2
            ratio = np.divide(
                3 * np.log1p(energy / 3), energy, out=np.ones_like(energy), where=energy > 1e-12
            )
            normalized = normalized * np.sqrt(ratio)
        r[self.phase_slice] = normalized
        return (r, diagnostics) if details else r


def run(case, methods=METHODS, modes=MODES):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    output = directory / "endpoints.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            no_evaluation_GPS_or_oracle_state=True,
            center=CENTER,
            grid=GRID,
            region_box_km=[[-12.5, 12.5]] * 2,
            raw_curved_only=True,
            modes=modes,
            gaussian_sigma_from_original_causal_bank=True,
            scales_are_successive_causal_prediction_disagreements_not_calibrated_covariances=True,
            student_phase_penalty="3*log(1+(phase/sigma)^2/3)",
            common_c0_center_nominations_and_3_geographic_starts=True,
            same_24_iteration_budget_for_c0_and_fitted_c=True,
            original_phase_bounds_still_15_seconds=True,
            physical_receiver_and_band_offset_drift_models_unchanged=True,
            source_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    Path(__file__).with_name("iterate_dsx01_position_nominations.py"),
                )
            },
        ),
    )
    for method in methods:
        seed = json.loads((NOMINATIONS / case / f"{method}_center.json").read_text())
        for mode in modes:
            if all(f"{mode}/{arm}/{method}" in results for arm in ("c0", "fitted_c")):
                continue

            def factory(scan, seed, method, fitted_c, anchor, prior=mode):
                return CausalPhaseFamilies(scan, seed, method, fitted_c, anchor, mode=prior)

            fits = fit_once(scan, seed, method, (0.0, 0.0), problem_class=factory)
            for arm, fit in fits.items():
                results[f"{mode}/{arm}/{method}"] = fit
            write(output, results)
            print(
                json.dumps(
                    dict(
                        case=case,
                        method=method,
                        mode=mode,
                        positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                        frequency_prior_scores={
                            arm: f["frequency_prior_score"] for arm, f in fits.items()
                        },
                    )
                ),
                flush=True,
            )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    args = parser.parse_args()
    run(args.case, methods=tuple(args.methods), modes=tuple(args.modes))
