"""Learn CFO uncertainty from raw graph polynomial residuals, before geography."""

import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from localize_merged_track_catalogue import raw_curvature
from prototype_dsx01_glrt_weighting import fit_variance


def estimate(tracks, observations):
    margins_by_id = {r["observation_id"]: r["fractional_margin"] for r in observations}
    margins, squares = [], []
    for track in tracks:
        t, y = np.array(track["times"]), np.array(track["values"])
        if not raw_curvature(dict(times=t, values=y)):
            continue
        for piece in track["pieces"]:
            use = (t >= piece["start_s"]) & (t <= piece["end_s"])
            degree = piece["degree"]
            if use.sum() < 2 * (degree + 1) + 3:
                continue
            times, values = t[use], y[use]
            z = (times - times.mean()) / max(1., float(np.ptp(times)))
            q, _ = np.linalg.qr(np.vander(z, degree + 1, increasing=True))
            leverage = np.sum(q**2, axis=1)
            residual = values - q @ (q.T @ values)
            squares.extend(residual**2 / (1 - leverage))
            margins.extend(margins_by_id[oid] for oid, active in zip(
                track["observation_ids"], use, strict=True) if active)
    if not squares:
        return dict(constant_radio_sigma_hz=150., extra_parameter_BIC_gain=0.,
                    noise_samples=0, per_observation_noise_sigma_hz={
                        r["observation_id"]: 150. for r in observations},
                    rule="no eligible radio-polynomial residuals; fixed 150 Hz fallback")
    m, s = np.array(margins), np.array(squares)
    constant = float(np.clip(s.mean(), 40**2, 600**2))
    floor, strength = fit_variance(m, s)
    proposed = np.clip(floor + strength / m, 40**2, 600**2)
    gain = float(np.sum(np.log(constant) + s / constant - np.log(proposed) - s / proposed))
    bic = gain - np.log(len(s))
    noise = {r["observation_id"]: float(np.sqrt(np.clip(
        floor + strength / r["fractional_margin"], 40**2, 600**2))) for r in observations}
    return dict(constant_radio_sigma_hz=float(np.sqrt(constant)),
                extra_parameter_BIC_gain=bic, noise_samples=len(s),
                floor_sigma_hz=float(np.sqrt(floor)), strength_hz2=float(strength),
                per_observation_noise_sigma_hz=noise,
                heteroscedastic_selected=bic > 0,
                rule=("floor + strength/margin; enable heteroscedasticity "
                      "only if extra BIC gain > 0"),
                model_is_uncertainty_proxy_not_calibrated_error_bar=True,
                no_GPS_TLE_or_satellite_residuals_used=True)


def run(directory):
    paths = [directory / "tracks.json", directory / "observations.json"]
    result = estimate(*(json.loads(p.read_text()) for p in paths))
    result["source_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result["code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write(directory / "radio_noise.json", result)


if __name__ == "__main__":
    root = (Path(__file__).resolve().parents[1]
            / "reports/2026_10_18_ds23_phase_refreshed_evaluation")
    for path in sorted(root.glob("DS*/prepared.json")):
        if json.loads(path.read_text())["status"] == "prepared":
            run(path.parent)
