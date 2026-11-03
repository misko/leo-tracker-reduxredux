"""Blind RF-by-time receiver drift ablation, without an evaluation position."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_dsx01_continuous_position import CENTER, GRID

OUTPUT = ROOT / "reports/2026_10_18_dsx01_rf_clock"
NOMINATIONS = ROOT / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32"


def rf_centres(tracks):
    """Instrument coordinate origins use RF metadata, never measured CFO."""
    groups = {}
    for t in tracks:
        key = (t["receiver"], int(t["channel"] > 4))
        groups.setdefault(key, set()).add(t["rf_hz"])
    return {key: np.mean(sorted(values)) for key, values in groups.items()}


class RFClockFamilies(AnchoredFamilies):
    """Add one RF-times-time coefficient per RX, shared across its bands."""

    def __init__(self, scan, seed, method, fitted_c, anchor, *, sigma=75.0):
        if not np.isfinite(sigma) or sigma <= 0:
            raise ValueError("positive finite receiver RF-drift prior required")
        self.base_size, self.clock_factor = None, None
        super().__init__(scan, seed, method, fitted_c, anchor)
        self.base_size = len(self.initial)
        self.sigma = sigma
        self.initial = np.r_[self.initial, [0.0, 0.0]]
        self.lower = np.r_[self.lower, [-10.0, -10.0]]
        self.upper = np.r_[self.upper, [10.0, 10.0]]
        centres = rf_centres(scan.tracks)
        self.clock_factor = np.zeros((len(self.flat_times), 2))
        for i, block in zip(self.members, self.slices, strict=True):
            t = scan.tracks[i]
            receiver = t["receiver"]
            reference = centres[receiver, int(t["channel"] > 4)]
            # f is expressed at 11.5 GHz; the caller subsequently multiplies q.
            self.clock_factor[block, receiver - 1] = (
                (t["rf_hz"] - reference) / 1e9 * (t["times"] - 150) / 150 / (t["rf_hz"] / 11.5e9)
            )

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["rf_drift_hz_per_ghz"] = np.asarray(x[self.base_size :]) * self.sigma
        return state

    def predicted(self, x):
        f, e = super().predicted(x)
        if self.clock_factor is not None:
            f += self.clock_factor @ self.decode(x)["rf_drift_hz_per_ghz"]
        return f, e

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        prior = np.asarray(x[self.base_size :])
        if details:
            r, diagnostics = result
            return np.r_[r, prior], diagnostics
        return np.r_[result, prior]


def run(case, methods=METHODS, sigmas=(0.0, 75.0, 300.0)):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    output = directory / "endpoints.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            no_evaluation_GPS_or_oracle_calibration=True,
            center=CENTER,
            region_box_km=[[-12.5, 12.5]] * 2,
            grid=GRID,
            max_iterations=24,
            common_c0_geographic_starts=3,
            receiver_clock_sigmas_hz_per_ghz=list(sigmas),
            receiver_clock_bound_sigma=10,
            RF_clock_basis="(RF-band_mean_RF)/1GHz * (time-150)/150; one coefficient per receiver",
            constant_RF_c0_fitted_c_arms_keep_same_points_labels_other_priors_and_search_budgets=True,
            raw_curved_only=True,
            original_receiver_band_offsets_and_linear_drifts_retained=True,
            shared_c0_blind_center_nomination_state_from_32_calibration_proposals=True,
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
        for sigma in sigmas:
            name = f"rf_sigma_{sigma:g}"
            if all(f"{name}/{arm}/{method}" in results for arm in ("c0", "fitted_c")):
                continue
            if sigma:

                def factory(scan, seed, method, fitted_c, anchor, scale=sigma):
                    return RFClockFamilies(scan, seed, method, fitted_c, anchor, sigma=scale)
            else:
                factory = AnchoredFamilies
            fits = fit_once(scan, seed, method, (0.0, 0.0), problem_class=factory)
            for arm, fit in fits.items():
                results[f"{name}/{arm}/{method}"] = fit
            write(output, results)
            print(
                json.dumps(
                    dict(
                        case=case,
                        method=method,
                        rf_sigma=sigma,
                        positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                        rf_drift={
                            arm: list(f["state"].get("rf_drift_hz_per_ghz", []))
                            for arm, f in fits.items()
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
    parser.add_argument("--sigmas", nargs="+", type=float, default=(0.0, 75.0, 300.0))
    args = parser.parse_args()
    run(args.case, methods=tuple(args.methods), sigmas=tuple(args.sigmas))
