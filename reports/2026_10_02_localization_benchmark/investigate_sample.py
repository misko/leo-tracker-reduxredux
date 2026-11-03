"""Post-fit diagnostics only; never modifies benchmark inputs or fitted parameters."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import models
import numpy as np
from bundle import Data
from evaluate import coordinates, ecef
from selection import MODEL_NAMES, ROOT

SESSION = "scan-fw-49d3aae278813149"
COLORS = ["#0072b2", "#d55e00"]


def local_displacement(point, reference):
    latitude, longitude = np.deg2rad(reference)
    difference = ecef(*coordinates(point)) - ecef(*reference)
    east = np.array([-np.sin(longitude), np.cos(longitude), 0])
    north = np.array(
        [
            -np.sin(latitude) * np.cos(longitude),
            -np.sin(latitude) * np.sin(longitude),
            np.cos(latitude),
        ]
    )
    return np.array([difference @ east, difference @ north])


def save(figure, output, name):
    figure.savefig(output / f"{name}.png", dpi=150, bbox_inches="tight")
    figure.savefig(output / f"{name}.svg", bbox_inches="tight")
    plt.close(figure)


def main():
    directory = ROOT / "scans" / SESSION
    output = ROOT / f"investigation-{SESSION}"
    output.mkdir(exist_ok=True)
    fits = json.loads((directory / "fits.json").read_text())["models"]
    truth = json.loads((directory / "evaluation.json").read_text())["reference_site"]
    reference = [truth["latitude_deg"], truth["longitude_deg"]]
    data = Data(directory)
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    independent = {row["track_index"]: row for row in fits["track_independent"]["tracks"]}
    times = np.linspace(0, 300, 301)
    palette = plt.get_cmap("tab20")
    errors = []
    figure, axes = plt.subplots(2, 2, figsize=(15, 12), constrained_layout=True)
    for index, name in enumerate(MODEL_NAMES):
        parameters = np.asarray(fits[name]["parameters"])
        error = float(np.linalg.norm(ecef(*coordinates(parameters[:2])) - ecef(*reference)))
        errors.append(error)
        displacement = local_displacement(parameters[:2], reference)
        axes[0, 0].scatter(*displacement, color=palette(index), s=70)
        axes[0, 0].annotate(str(index + 1), displacement, xytext=(5, 3), textcoords="offset points")
        if name != "track_independent":
            for receiver in (0, 1):
                line = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (times - 150)
                axes[1, receiver].plot(
                    times,
                    line / 1000,
                    color=palette(index),
                    label=f"{index + 1}: {name}",
                    alpha=0.8,
                )
    axes[0, 0].scatter(0, 0, marker="*", s=220, c="black", label="Reference site")
    axes[0, 0].set(
        xlabel="East of reference (km)",
        ylabel="North of reference (km)",
        title="Fitted positions (numbers match method list)",
        aspect="equal",
    )
    axes[0, 0].legend()
    axes[0, 1].barh(range(13), errors, color=[palette(index) for index in range(13)])
    axes[0, 1].set_yticks(
        range(13), [f"{index + 1}: {name}" for index, name in enumerate(MODEL_NAMES)]
    )
    axes[0, 1].invert_yaxis()
    axes[0, 1].set(xlabel="Reference error (km)", title="All 13 completed fits")
    for receiver in (0, 1):
        axes[1, receiver].set(
            xlabel="Scan time (s)",
            ylabel="LNB correction (kHz)",
            title=f"RX{receiver}: fitted shared lines (not independent offsets)",
        )
        axes[1, receiver].grid(alpha=0.2)
    axes[1, 1].legend(fontsize=7, ncol=2)
    figure.suptitle(SESSION + " — position and RX corrections", fontsize=15)
    save(figure, output, "01-positions-and-rx")

    offsets_figure, offsets_axes = plt.subplots(
        4, 4, figsize=(19, 15), sharex=True, sharey=True, constrained_layout=True
    )
    residual_figure, residual_axes = plt.subplots(
        4, 4, figsize=(19, 15), sharex=True, sharey=True, constrained_layout=True
    )
    diagnostics = {}
    group_details = {}
    track_records = []
    for index, name in enumerate(MODEL_NAMES):
        parameters = np.asarray(fits[name]["parameters"])
        no_rx = parameters.copy()
        no_rx[2:6] = 0
        prediction, visible = data.predict(no_rx)
        blocks = models._track_blocks(context, prediction, visible)
        offset_axis = offsets_axes.flat[index]
        residual_axis = residual_axes.flat[index]
        points = []
        for block in blocks:
            selected = independent[block["track_index"]]
            if not selected["accepted"]:
                continue
            satellite = selected["satellite_index"]
            receiver = block["receiver"]
            offset = float(models._robust_column_locations(block["residual"][:, [satellite]])[0])
            center = float((np.min(block["times"]) + np.max(block["times"])) / 2 + 150)
            duration = float(np.ptp(block["times"]))
            expected = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (center - 150)
            branch_center = expected if name != "track_independent" else 92000.0
            lifted = float(models.circular(offset, branch_center) + branch_center)
            delta = (
                float(models.circular(offset, expected)) if name != "track_independent" else None
            )
            points.append(
                {
                    "track_index": block["track_index"],
                    "rx": receiver,
                    "channel": int(data.channel[block["rows"][0]]),
                    "catalog_number": int(data.numbers[satellite]),
                    "center_s": center,
                    "duration_s": duration,
                    "offset_hz": lifted,
                    "minus_shared_line_hz": delta,
                    "observations": len(block["rows"]),
                }
            )
            offset_axis.scatter(
                center, lifted / 1000, color=COLORS[receiver], s=12 + duration / 3, alpha=0.65
            )
        if name != "track_independent":
            for receiver in (0, 1):
                line = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (times - 150)
                offset_axis.plot(times, line / 1000, color=COLORS[receiver])
            details = models._glrt_details(context, parameters, 64)
            group_details[name] = details
            rows = details["rows"]
            for receiver in (0, 1):
                selected = (data.receiver[rows] == receiver) & np.isfinite(details["errors"])
                residual_axis.scatter(
                    data.times[rows[selected]],
                    details["errors"][selected],
                    s=2,
                    alpha=0.25,
                    color=COLORS[receiver],
                    rasterized=True,
                )
            diagnostics[name] = {
                "reference_error_km": errors[index],
                "common64_loss": details["objective"],
                "within_1000hz": int(np.sum(np.abs(details["errors"]) < 1000)),
                "rx_parameters": parameters[2:6].tolist(),
                "track_points": points,
            }
        else:
            diagnostics[name] = {"reference_error_km": errors[index], "track_points": points}
            residual_axis.text(
                0.5,
                0.5,
                "No scan-wide RX model\nCommon-64 diagnostic not applicable",
                transform=residual_axis.transAxes,
                ha="center",
            )
            track_records = points
        offset_axis.set_title(f"{index + 1}: {name}", fontsize=9)
        residual_axis.set_title(f"{index + 1}: {name}", fontsize=9)
        offset_axis.grid(alpha=0.2)
        residual_axis.axhline(0, color="black", lw=0.5)
    for index in range(13, 16):
        offsets_axes.flat[index].set_visible(False)
        residual_axes.flat[index].set_visible(False)
    offsets_axes.flat[0].set(xlim=(0, 300), ylim=(70, 115))
    residual_axes.flat[0].set(xlim=(0, 300), ylim=(-2000, 2000))
    offsets_figure.supxlabel("Scan time (s); point size indicates track duration")
    offsets_figure.supylabel("Per-track constant offset (kHz), alias branch near RX line")
    offsets_figure.suptitle(
        "Same track IDs and independent-fit satellite identities in every panel\n"
        "Recomputed at each fitted position/timing; blue RX0, orange RX1; "
        "lines are fitted RX corrections",
        fontsize=13,
    )
    residual_figure.supxlabel("Scan time (s)")
    residual_figure.supylabel("Observed minus nearest visible curve (Hz); display clipped at ±2000")
    residual_figure.suptitle(
        "Common 64-satellite raw-GLRT residual diagnostic — NOT each fitted objective\n"
        "One alternative per source group; blue RX0, orange RX1",
        fontsize=13,
    )
    save(offsets_figure, output, "02-track-offsets-all-variants")
    save(residual_figure, output, "03-glrt-residuals-all-variants")

    figure, axes = plt.subplots(1, 3, figsize=(18, 5), constrained_layout=True)
    baseline = group_details["glrt_fixed_64"]
    for axis, name in zip(
        axes, ["glrt_timing_3s", "glrt_timing_10s", "coherent_timing"], strict=True
    ):
        details = group_details[name]
        counts = np.bincount(details["satellites"][np.abs(details["errors"]) < 1000], minlength=64)
        used = np.flatnonzero(counts)
        shifts = np.asarray(fits[name]["parameters"])[6:]
        axis.scatter(shifts[used], counts[used], s=35, color="#0072b2")
        for satellite in used:
            if counts[satellite] >= 80 or abs(shifts[satellite]) >= 2.9:
                axis.annotate(
                    str(data.numbers[satellite]),
                    (shifts[satellite], counts[satellite]),
                    fontsize=6,
                    xytext=(3, 3),
                    textcoords="offset points",
                )
        axis.axvline(0, color="gray", lw=0.6)
        axis.set(
            title=name, xlabel="Satellite time shift (s)", ylabel="Common-64 groups within 1 kHz"
        )
        axis.grid(alpha=0.2)
        changed = details["satellites"] != baseline["satellites"]
        diagnostics[name]["identity_changes_from_fixed64"] = int(np.sum(changed))
        diagnostics[name]["timing_used_satellites"] = [
            {
                "catalog_number": int(data.numbers[satellite]),
                "tau_s": float(shifts[satellite]),
                "groups_within_1000hz": int(counts[satellite]),
            }
            for satellite in used
        ]
    figure.suptitle(
        "Timing freedom and recovered raw-GLRT support (common diagnostic, not anchor assignment)"
    )
    save(figure, output, "04-satellite-timing")
    for name in ("track_constant", "track_linear"):
        selected = {row["track_index"]: row for row in fits[name]["tracks"]}
        diagnostics[name]["satellite_changes_from_independent"] = sum(
            row["satellite_index"] != independent[index]["satellite_index"]
            for index, row in selected.items()
        )
        diagnostics[name]["accepted_tracks"] = sum(row["accepted"] for row in selected.values())
    payload = {
        "session_id": SESSION,
        "diagnostics": diagnostics,
        "longest_independent_tracks": sorted(track_records, key=lambda row: -row["duration_s"])[
            :10
        ],
        "note": "Diagnostic only: fixed independent identities are hypotheses, not truth. "
        "Raw-GLRT nearest-curve scores are not comparable to whole-track loss.",
    }
    (output / "diagnostics.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
