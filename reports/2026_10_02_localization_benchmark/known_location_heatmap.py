"""Truth-conditioned diagnostic sweep, separate from localization benchmark fits."""

import hashlib
import json
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import models
import numpy as np
from bundle import Data
from evaluate import coordinates
from investigate_sample import SESSION, save
from selection import ROOT

ALIAS = models.ALIAS_HZ


def position_from_latlon(latitude, longitude):
    origin_lat, origin_lon = np.deg2rad([38.5816, -121.4944])
    target_lat, target_lon = np.deg2rad([latitude, longitude])
    difference = target_lon - origin_lon
    east = np.sin(difference) * np.cos(target_lat)
    north = np.cos(origin_lat) * np.sin(target_lat) - np.sin(origin_lat) * np.cos(
        target_lat
    ) * np.cos(difference)
    cosine = np.sin(origin_lat) * np.sin(target_lat) + np.cos(origin_lat) * np.cos(
        target_lat
    ) * np.cos(difference)
    angle = np.arctan2(np.hypot(east, north), cosine)
    bearing = np.arctan2(east, north)
    return 6371.0088 * angle * np.array([np.sin(bearing), np.cos(bearing)])


def prepare_groups(data, prediction, visible, receiver):
    rows = np.flatnonzero(data.receiver == receiver)
    groups = []
    for group in np.unique(data.group[rows]):
        selected = rows[data.group[rows] == group]
        residual = data.measured[selected, None] - prediction[selected]
        times = np.broadcast_to(data.times[selected, None] - 150, residual.shape)
        usable = visible[selected] & np.isfinite(residual)
        groups.append((residual[usable], times[usable]))
    return groups


def intercept_losses(groups, intercepts, slope):
    queries = np.mod(intercepts, ALIAS)
    accumulated = np.zeros(len(queries))
    for residual, times in groups:
        if not len(residual):
            accumulated += models.UNMATCHED_COST
            continue
        candidates = np.sort(np.mod(residual - slope * times, ALIAS))
        extended = np.r_[candidates[-1] - ALIAS, candidates, candidates[0] + ALIAS]
        right = np.searchsorted(extended, queries)
        distances = np.minimum(extended[right] - queries, queries - extended[right - 1])
        accumulated += models.rho(distances)
    return accumulated / len(groups)


def sweep(groups, intercepts, slopes, label):
    result = np.empty((len(slopes), len(intercepts)))
    started = time.monotonic()
    for index, slope in enumerate(slopes):
        result[index] = intercept_losses(groups, intercepts, slope)
        if index % 50 == 0 or index == len(slopes) - 1:
            print(
                json.dumps(
                    {
                        "stage": label,
                        "rows": index + 1,
                        "total": len(slopes),
                        "elapsed_s": time.monotonic() - started,
                    }
                ),
                flush=True,
            )
    return result


def minimum(loss, intercepts, slopes):
    row, column = np.unravel_index(np.argmin(loss), loss.shape)
    return {
        "intercept_hz_at_150s": float(intercepts[column]),
        "slope_hz_s": float(slopes[row]),
        "loss": float(loss[row, column]),
        "slope_at_edge": row in (0, len(slopes) - 1),
        "intercept_at_edge": column in (0, len(intercepts) - 1),
    }


def main():
    directory = ROOT / "scans" / SESSION
    output = ROOT / f"investigation-{SESSION}"
    data = Data(directory)
    evaluation = json.loads((directory / "evaluation.json").read_text())
    truth = evaluation["reference_site"]
    parameters = np.zeros(70)
    parameters[:2] = position_from_latlon(truth["latitude_deg"], truth["longitude_deg"])
    np.testing.assert_allclose(
        coordinates(parameters[:2]), [truth["latitude_deg"], truth["longitude_deg"]], atol=1e-10
    )
    prediction, visible = data.predict(parameters)
    fits = json.loads((directory / "fits.json").read_text())["models"]
    intercepts = np.linspace(0, ALIAS, 910, endpoint=False)
    slopes = np.arange(-200, 201, 2.0)
    archive = {"coarse_intercepts_hz": intercepts, "coarse_slopes_hz_s": slopes}
    report = {
        "session_id": SESSION,
        "reference_site": truth,
        "fixed_position": parameters[:2].tolist(),
        "definition": "All raw source groups, nearest visible alternative among frozen "
        "64 satellites; equal group weights; capped soft-L1, scale 200 Hz, "
        "cap 2000 Hz. Satellite timing shifts fixed at zero. "
        "Intercept at t=150 s, circular alias period 227272.727 Hz. "
        "Zero-altitude propagation convention retained from benchmark.",
        "scope": "Truth-conditioned diagnostic, NOT a localization estimate or validation.",
        "bundle_sha256": hashlib.sha256((directory / "bundle.npz").read_bytes()).hexdigest(),
        "receivers": {},
    }
    figure, axes = plt.subplots(2, 2, figsize=(16, 11), constrained_layout=True)
    started = time.monotonic()
    for receiver in (0, 1):
        groups = prepare_groups(data, prediction, visible, receiver)
        coarse = sweep(groups, intercepts, slopes, f"RX{receiver} coarse")
        best = minimum(coarse, intercepts, slopes)
        fine_intercepts = best["intercept_hz_at_150s"] + np.arange(-5000, 5001, 25.0)
        fine_slopes = best["slope_hz_s"] + np.arange(-12, 12.01, 0.2)
        fine = sweep(groups, fine_intercepts, fine_slopes, f"RX{receiver} fine")
        fine_best = minimum(fine, fine_intercepts, fine_slopes)
        bounded_slopes = np.arange(-10, 10.01, 0.2)
        bounded = sweep(groups, intercepts, bounded_slopes, f"RX{receiver} bounded full alias")
        bounded_best = minimum(bounded, intercepts, bounded_slopes)
        bounded_intercepts = bounded_best["intercept_hz_at_150s"] + np.arange(-500, 501, 10.0)
        bounded_fine = sweep(
            groups, bounded_intercepts, bounded_slopes, f"RX{receiver} bounded fine"
        )
        bounded_best = minimum(bounded_fine, bounded_intercepts, bounded_slopes)
        old = np.asarray(fits["track_linear"]["parameters"])[2 + 2 * receiver : 4 + 2 * receiver]
        report["receivers"][str(receiver)] = {
            "groups": len(groups),
            "coarse_best": best,
            "refined_best": fine_best,
            "within_10hz_s_best": bounded_best,
            "old_shared_line_at_known_location": {
                "intercept_hz_at_150s": float(old[0]),
                "slope_hz_s": float(old[1]),
                "loss": float(intercept_losses(groups, [old[0]], old[1])[0]),
            },
        }
        for name, values in (
            ("coarse_loss", coarse),
            ("fine_loss", fine),
            ("fine_intercepts_hz", fine_intercepts),
            ("fine_slopes_hz_s", fine_slopes),
            ("bounded_loss", bounded),
            ("bounded_slopes_hz_s", bounded_slopes),
            ("bounded_fine_loss", bounded_fine),
            ("bounded_fine_intercepts_hz", bounded_intercepts),
        ):
            archive[f"rx{receiver}_{name}"] = values
        for column, horizontal, vertical, loss in (
            (0, intercepts, slopes, coarse),
            (1, fine_intercepts, fine_slopes, fine),
        ):
            axis = axes[receiver, column]
            view = axis.pcolormesh(
                horizontal / 1000,
                vertical,
                loss / 1000,
                shading="auto",
                cmap="viridis_r",
                rasterized=True,
            )
            for bound in (-10, 10):
                if vertical.min() <= bound <= vertical.max():
                    axis.axhline(bound, color="white", linestyle="--", linewidth=0.8)
            axis.scatter(
                fine_best["intercept_hz_at_150s"] / 1000,
                fine_best["slope_hz_s"],
                marker="*",
                s=140,
                c="red",
                label="Refined minimum",
            )
            if (
                horizontal.min() <= old[0] <= horizontal.max()
                and vertical.min() <= old[1] <= vertical.max()
            ):
                axis.scatter(
                    old[0] / 1000,
                    old[1],
                    marker="x",
                    s=70,
                    c="cyan",
                    label="Previous joint-fit RX line",
                )
            axis.set(
                title=f"RX{receiver}: "
                + (
                    "full alias-period sweep"
                    if column == 0
                    else "refinement near best coarse basin"
                ),
                xlabel="Intercept at 150 s (kHz)",
                ylabel="Slope (Hz/s)",
            )
            axis.legend(fontsize=8)
            figure.colorbar(
                view, ax=axis, label="Mean capped soft-L1 loss / 1000 (lower is better)"
            )
        np.savez_compressed(output / "known-location-heatmaps.npz", **archive)
        (output / "known-location-heatmaps.json").write_text(json.dumps(report, indent=2) + "\n")
    report["elapsed_s"] = time.monotonic() - started
    report["evaluated_grid_cells"] = int(
        sum(value.size for key, value in archive.items() if "loss" in key)
    )
    (output / "known-location-heatmaps.json").write_text(json.dumps(report, indent=2) + "\n")
    figure.suptitle(
        SESSION + " — raw-GLRT loss with location fixed to the known site\n"
        "All 64 candidates; no satellite time shifts; dashed lines mark ±10 Hz/s",
        fontsize=13,
    )
    save(figure, output, "08-known-location-glrt-heatmap")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
