"""Post-fit debug report: calibration residuals, profile traps and sensitivity."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from joint_inputs import _coordinates, _ecef
from oracle_position_diagnostic import reference_coordinates
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibratedLikelihood, rf_features
from soft_likelihood import SoftLikelihood
from timing_model import TimingObjective


def residual_channels(data, predicted, posterior):
    rows = np.arange(len(data.times))
    winner = posterior.argmax(axis=1)
    confident = posterior[rows, winner] >= 0.8
    residual = circular_residual(data.measured, predicted[rows, winner])
    result = []
    for receiver in (0, 1):
        for channel in np.unique(data.channel):
            selected = confident & (data.receiver == receiver) & (data.channel == channel)
            result.append({"receiver": receiver, "channel": int(channel),
                           "rows": int(selected.sum()),
                           "mean_hz": float(residual[selected].mean()) if selected.any() else None,
                           "median_hz": float(np.median(residual[selected]))
                           if selected.any() else None})
    return result


def build():
    destination = ROOT / "wrong-solution-summary.json"
    if destination.exists():
        raise FileExistsError(destination)
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    hashes = snapshot_files([__file__])
    reports = []

    def read(path):
        record = json.loads(path.read_text())
        if "source_hashes" in record:
            assert_snapshot_unchanged(record["source_hashes"])
        hashes.update(snapshot_files([path]))
        return record

    for session in sessions:
        reference = read(ROOT / "scans" / session / "evaluation.json")["reference_site"]
        truth = _ecef(reference["latitude_deg"], reference["longitude_deg"])
        true_position = reference_coordinates(reference["latitude_deg"], reference["longitude_deg"])
        parent = read(ROOT / "runs-continuation" / session / "medium" / "fit.json")
        satellites = np.asarray(parent["fit"]["satellite_indices"], dtype=int)
        _, data = load_scan(session)
        states = {"original": parent}
        for name in ("common", "per-rx"):
            states[name] = read(ROOT / "rf-calibration-diagnostic" / f"{session}-{name}.json")
        for name in ("rx0", "rx1", "omit"):
            states[name] = read(ROOT / "receiver-satellite-ablation" / f"{session}-{name}.json")
        attribution = read(ROOT / "wrong-solution-attribution" / session / "attribution.json")
        profile = read(ROOT / "profile-path-diagnostic" / f"{session}.json")
        rows = []
        for name, record in states.items():
            fitted = record["fit"]
            parameters = np.asarray(fitted["parameters"])
            estimate = _ecef(*_coordinates(parameters[:2]))
            row = {"variant": name, "position_error_km": float(np.linalg.norm(estimate - truth)),
                   "displacement_east_north_km": (parameters[:2] - true_position).tolist(),
                   "objective": fitted["objective"], "success": fitted["success"],
                   "effective_ppm": fitted.get("effective_ppm"),
                   "elapsed_s": fitted["elapsed_s"]}
            if name in ("original", "common", "per-rx"):
                prepared = prepare_finite_set_likelihood(data.measured, data.group)
                if name == "original":
                    likelihood = SoftLikelihood(prepared, 0.8 / len(satellites))
                    correction = np.zeros(len(data.times))
                else:
                    _, features = rf_features(data.rf, data.receiver, name == "per-rx")
                    likelihood = CalibratedLikelihood(prepared, 0.8 / len(satellites), features)
                    likelihood.coefficients = np.asarray(fitted["rf_coefficient_hz_per_ghz"])
                    correction = features @ likelihood.coefficients
                objective = TimingObjective(data, parameters, satellites, likelihood, 200.)
                value, _ = objective.evaluate(np.asarray(fitted["vector"]))
                if not np.isclose(value, fitted["objective"], rtol=0, atol=1e-6):
                    raise ValueError("calibration report does not reproduce fitted loss")
                prediction, _ = objective.predict(np.asarray(fitted["vector"]))
                row["confident_residual_by_channel"] = residual_channels(
                    data, prediction + correction[:, None],
                    likelihood.last_result["row_association_probability"])
            rows.append(row)
        tracks = attribution["seed_track_agreement"]
        reports.append({"session": session, "variants": rows,
                        "seed_tracks": len(tracks),
                        "seed_tracks_with_mean_posterior_below_001": sum(
                            row["free"]["mean_association"] is not None
                            and row["free"]["mean_association"] < 0.01 for row in tracks),
                        "old_oracle_truth_gap": profile["previous_oracle_truth_objective"]
                        - profile["start_objective"],
                        "continued_oracle_truth_gap": profile["truth_minus_start_objective"],
                        "profile_fractions": profile["fractions"],
                        "profile_objectives": [row["objective"] for row in profile["stations"]]})
    result = {"schema": "ds13-wrong-solution-summary/v1", "scans": reports,
              "source_hashes": hashes,
              "scope": "Reference-informed development debugging, no held-out validation. "
                       "Receiver and emitter ablations are sensitivity checks, not selection rules. "
                       "RF calibration alone is not a demonstrated localization improvement. "
                       "Residual statistics use each fitted model's posterior winner >=0.8."}
    assert_snapshot_unchanged(hashes)
    with destination.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def plot(result):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(13, 10))
    colors = {"original": "C0", "common": "C1", "rx0": "C2", "rx1": "C3", "omit": "C4"}
    for column, scan in enumerate(result["scans"]):
        for row in scan["variants"]:
            name = row["variant"]
            if name == "per-rx":
                continue
            if name in ("original", "common"):
                for receiver, style in ((0, "-"), (1, "--")):
                    bins = [item for item in row["confident_residual_by_channel"]
                            if item["receiver"] == receiver]
                    axes[0, column].plot([item["channel"] for item in bins],
                                         [item["mean_hz"] for item in bins], linestyle=style,
                                         marker="o", color=colors[name], label=f"{name}, RX{receiver}")
            east, north = row["displacement_east_north_km"]
            axes[1, column].scatter(east, north, color=colors[name], s=65,
                                    label=f"{name}: {row['position_error_km']:.2f} km")
        axes[0, column].set_title(scan["session"])
        axes[0, column].axhline(0, color="gray", linestyle=":")
        axes[0, column].set_xticks([1, 2, 3, 4])
        axes[0, column].set_xlabel("Channel")
        axes[1, column].scatter(0, 0, marker="*", s=160, color="black", label="Known position")
        axes[1, column].set_xlabel("East displacement (km)")
        axes[1, column].set_aspect("equal", adjustable="datalim")
        for axis in axes[:, column]:
            axis.grid(alpha=0.25)
            axis.legend(fontsize=8)
    axes[0, 0].set_ylabel("Mean confident frequency residual (Hz)")
    axes[1, 0].set_ylabel("North displacement (km)")
    figure.suptitle("DS13 debugging: channel calibration fixes residual structure, not all position bias")
    figure.tight_layout()
    figure.savefig(ROOT / "wrong-solution-debug.png", dpi=150)
    figure.savefig(ROOT / "wrong-solution-debug.svg")
    plt.close(figure)


if __name__ == "__main__":
    result = build()
    plot(result)
    for scan in result["scans"]:
        print(json.dumps(scan), flush=True)
