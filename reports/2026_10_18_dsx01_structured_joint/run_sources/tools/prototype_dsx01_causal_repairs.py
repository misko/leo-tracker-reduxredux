"""Three causal repairs with matched blind grid and c-arm controls."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import OUTPUT, forecast_bank
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_dsx01_family_consensus import ConsensusFamilies
from prototype_dsx01_receiver_geometry import SOURCE, geometry_problem
from prototype_s01_receiver_drift import ReceiverDriftProblem


def temporal_curvature(times):
    """Two fixed scan-wide Legendre modes, with no affine component."""
    z = (np.asarray(times) - 150.0) / 150.0
    return np.column_stack(((3 * z**2 - 1) / 2, (5 * z**3 - 3 * z) / 2))


class BandCurvatureFamilies(AnchoredFamilies):
    def __init__(self, *args, common_sigma=300.0, contrast_sigma=100.0):
        self.base_size = None
        super().__init__(*args)
        self.base_size = len(self.initial)
        self.radio_keys = [
            (kind, receiver, mode)
            for kind in (
                ("contrast",) if self.method == "receiver_smooth" else ("common", "contrast")
            )
            for receiver in range(2)
            for mode in range(2)
        ]
        self.radio_scales = np.array(
            [common_sigma if k[0] == "common" else contrast_sigma for k in self.radio_keys]
        )
        self.initial = np.r_[self.initial, np.zeros(len(self.radio_keys))]
        self.lower = np.r_[self.lower, np.full(len(self.radio_keys), -5.0)]
        self.upper = np.r_[self.upper, np.full(len(self.radio_keys), 5.0)]

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["radio_curvature_hz"] = np.asarray(x[self.base_size :]) * self.radio_scales
        return state

    def predicted(self, x):
        f, e = super().predicted(x)
        if self.base_size is None:
            return f, e
        amplitudes = np.asarray(x[self.base_size :]) * self.radio_scales
        for i, block in zip(self.members, self.slices, strict=True):
            track = self.scan.tracks[i]
            basis = temporal_curvature(track["times"])
            # channel band convention is the same as Scan.hardware.
            band = int(track["channel"] > 4)
            sign = -1.0 if band == 0 else 1.0
            for (kind, receiver, mode), a in zip(self.radio_keys, amplitudes, strict=True):
                if receiver == track["receiver"] - 1:
                    f[block] += basis[:, mode] * a * (sign if kind == "contrast" else 1)
        return f, e

    def residual(self, x, *, details=False):
        value = super().residual(x, details=details)
        # Prefix extra priors so the RX wrapper's existing tail offsets remain exact.
        prior = np.asarray(x[self.base_size :])
        return (np.r_[prior, value[0]], value[1]) if details else np.r_[prior, value]


class ForecastFamilies(AnchoredFamilies):
    def __init__(self, *args):
        super().__init__(*args)
        bank, self.forecast_metadata = forecast_bank(self.scan, self.labels)
        self.sky = dict(
            time_s=bank["time_s"],
            position_km=bank["position_km"][self.labels],
            velocity_km_s=bank["velocity_km_s"][self.labels],
        )


def repair_problem(*args, variant):
    if variant == "baseline":
        return geometry_problem(*args, mean_sigma=10, height_sigma=0)
    if variant == "causal_forecast":
        problem = ForecastFamilies(*args)
    elif variant == "family_consensus":
        problem = ConsensusFamilies(*args, mode="consensus_floor")
    elif variant == "band_curvature":
        problem = BandCurvatureFamilies(*args)
    else:
        raise ValueError("unknown repair")
    return ReceiverDriftProblem(problem, mean_sigma=10)


def run(case, method, variants):
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    scan = Scan(case)
    seed_path = SOURCE / case / f"{method}_center.json"
    seed = json.loads(seed_path.read_text())
    locked = geometry_problem(
        scan, seed, method, False, (0, 0), mean_sigma=10, height_sigma=0
    ).alias
    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_TLE_input=True,
            same_original_curved_observations_nominations_aliases_and_center_seed=True,
            c_arms_share_original_grid_3_starts_24_iterations=True,
            receiver_mean_sigma_hz_s=10,
            receiver_band_contrast_sigma_hz_s=0.5,
            band_shape_prior_reference_hz=dict(common=300, contrast=100),
            band_shape_orders=[2, 3],
            family_consensus_cap_per_normalized_point=4,
            variants=variants,
            seed_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for variant in variants:
        if all(f"{variant}/{a}" in results for a in ("c0", "fitted_c")):
            continue

        def factory(*args, name=variant):
            p = repair_problem(*args, variant=name)
            p.problem.alias = list(locked)
            return p

        fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
        for arm, fit in fits.items():
            results[f"{variant}/{arm}"] = fit
        write(path, results)
        if variant == "causal_forecast":
            write(directory / "forecast_metadata.json", scan.causal_forecast_cache[1])
        print(case, method, variant, {a: f["east_north_km"] for a, f in fits.items()}, flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, required=True)
    p.add_argument(
        "--variants", nargs="+", default=["causal_forecast", "family_consensus", "band_curvature"]
    )
    args = p.parse_args()
    run(args.case, args.method, args.variants)
