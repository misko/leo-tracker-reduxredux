"""Learn a noise feature from saved per-frame CFO scatter, before geography.

This uses existing remeasurement JSON only. Per-frame scatter is an uncertainty
proxy, not an independently calibrated error bar. Radio-polynomial residuals
learn its scale and a floor, without GPS or satellite residuals.
"""

import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from prototype_dsx01_glrt_weighting import fit_variance, variance_samples
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import measurement_path

OUTPUT = ROOT / "reports/2026_10_18_dsx01_window_uncertainty"


def frame_scatter(times, frequencies, margins):
    t, f, m = (np.asarray(x, float) for x in (times, frequencies, margins))
    if t.ndim != 1 or f.shape != t.shape or m.shape != t.shape:
        raise ValueError("matching per-frame times, CFOs and quality margins required")
    good = np.isfinite(t) & np.isfinite(f) & np.isfinite(m) & (m >= 0.02) & (abs(f) <= 750)
    t, f, m = t[good], f[good], m[good]
    if len(t) < 6 or np.ptp(t) < 0.007:
        return None
    weights = np.minimum(m**2, 4 * np.median(m**2))
    design = np.column_stack((np.ones(len(t)), t))
    influence = np.linalg.solve(design.T @ (weights[:, None] * design), design.T * weights)
    coefficient = influence @ f
    residual = f - design @ coefficient
    scatter = float(residual @ residual / (len(t) - 2))
    return dict(
        variance_feature_hz2=max(1.0, float(scatter * (influence[0] @ influence[0]))),
        frames=len(t),
        frame_scatter_hz=float(np.sqrt(scatter)),
    )


def run():
    OUTPUT.mkdir(exist_ok=True)
    results = {}
    for case in (f"DSX01-S0{k}" for k in range(1, 6)):
        source = measurement_path(case)
        points = json.loads(source.read_text())["points"]
        features = {}
        for oid, row in points.items():
            frame = row["midpoint300"]
            result = frame_scatter(
                frame.get("frame_time_from_midpoint_s", []),
                frame.get("frame_frequencies_hz", []),
                frame.get("frame_margins", []),
            )
            features[oid] = result
        values = [r["variance_feature_hz2"] for r in features.values() if r is not None]
        median = float(np.median(values))
        normalized = {
            oid: (r["variance_feature_hz2"] / median if r is not None else 1.0)
            for oid, r in features.items()
        }
        feature_scores = {
            oid: {"fractional_margin": 1 / value} for oid, value in normalized.items()
        }
        scan = Scan(case)
        apply_measurements(scan, points, "glrt300")
        margins, squares = variance_samples(scan, feature_scores)
        floor, strength = fit_variance(margins, squares)
        variance = np.clip(floor + strength / margins, 40**2, 600**2)
        constant = float(np.mean(squares))
        gain = float(
            np.sum(np.log(constant) + squares / constant - np.log(variance) - squares / variance)
        )
        noise = {
            oid: float(np.sqrt(np.clip(floor + strength * value, 40**2, 600**2)))
            for oid, value in normalized.items()
        }
        results[case] = dict(
            original_points=len(points),
            valid_frame_features=len(values),
            fallback=len(points) - len(values),
            median_variance_feature_hz2=median,
            fitted_floor_sigma_hz=float(np.sqrt(floor)),
            fitted_strength_hz2=float(strength),
            constant_radio_sigma_hz=float(np.sqrt(constant)),
            Gaussian_noise_cost_gain=gain,
            extra_parameter_BIC_gain=gain - np.log(len(squares)),
            radio_polynomial_noise_samples=len(squares),
            noise_sigma_quantiles_hz=np.quantile(list(noise.values()), [0, 0.1, 0.5, 0.9, 1]),
            feature_quantiles_hz2=np.quantile(values, [0, 0.1, 0.5, 0.9, 1]),
            per_observation_noise_sigma_hz=noise,
            frame_features=features,
            measurement_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        print(
            json.dumps(
                dict(
                    case=case,
                    noise_cost_gain=gain,
                    BIC_gain=results[case]["extra_parameter_BIC_gain"],
                    floor_hz=float(np.sqrt(floor)),
                    strength=float(strength),
                )
            ),
            flush=True,
        )
    write(OUTPUT / "noise_features.json", results)
    write(
        OUTPUT / "protocol.json",
        dict(
            no_GPS_or_satellite_residuals_in_noise_fit=True,
            no_new_IQ_reads_or_RF_collection=True,
            observations_and_GLRT_CFO_values_preserved=True,
            original_curved_radio_polynomial_pieces_and_leverage_correction=True,
            frame_quality="margin >=.02, |residual CFO|<=750 Hz, at least 6 frames spanning 7 ms",
            variance_model="floor + strength * normalized frame-intercept-scatter feature",
            fallback_feature="case median; detection retained",
            variance_floor_bounds_hz=[40.0, 600.0],
            variance_feature_is_proxy_not_calibrated_confidence=True,
            data_selection_rule="enable feature only if extra-parameter radio-noise BIC gain > 0",
        ),
    )


if __name__ == "__main__":
    run()
