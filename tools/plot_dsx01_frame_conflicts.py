"""Inspect timing-linked GLRT subsets under existing blind satellite hypotheses."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from dsx01_cut_linear import curve_posterior, transfer_design
from probe_dsx01_cut_linear import prepare
from profile_dsx01_geographic_calibration import OUTPUT as FRAME
from run_dsx01_frame_joint import OUTPUT

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run():
    frames = json.loads((FRAME / "frame_coherent_calibration.json").read_text())
    for case in ["DSX01-S01", "DSX01-S04"]:
        scan, fits, parents, _, _ = prepare(case)
        p = parents["c0"]
        fit = fits["c0"]
        x = np.asarray(fit["parameters"])
        result, _ = curve_posterior(p, x)
        directory = OUTPUT / "identity_probe" / case
        proposals = json.loads((directory / "proposals.json").read_text())["proposals"]
        by_key = {t["key"]: t for t in scan.tracks}
        label = {r["component"]: r["candidate_index"] for r in fit["rows"]}
        summary = []
        for edge_index, proposal in enumerate(proposals):
            keys = [proposal["edge"]["left"], proposal["edge"]["right"]]
            populations = [set(by_key[key]["observation_ids"]) for key in keys]
            shared = set()
            for pair in frames[case]["pairs"]:
                ids = set(pair["observation_ids"])
                if (
                    pair["frame_coherent"]
                    and pair["both_original_curved"]
                    and all(ids & population for population in populations)
                ):
                    shared.update(ids)
            candidates = [label[key] for key in keys]
            fig, axes = plt.subplots(2, 2, figsize=(15, 8))
            for col, key in enumerate(keys):
                t = by_key[key]
                times = t["times"]
                values = t["values"]
                matched = np.array([oid in shared for oid in t["observation_ids"]])
                axes[0, col].scatter(times, values, s=14, label="GLRT300 CFO")
                axes[0, col].scatter(
                    times[matched],
                    values[matched],
                    s=35,
                    facecolors="none",
                    edgecolors="red",
                    label="Timing-linked points",
                )
                for piece in t["pieces"]:
                    tt = np.linspace(piece["start_s"], piece["end_s"], 100)
                    yy = np.polynomial.polynomial.polyval(
                        (tt - piece["reference_time_s"]) / piece["time_scale_s"],
                        piece["coefficients_hz"],
                    )
                    axes[0, col].plot(
                        tt,
                        yy,
                        color="green",
                        alpha=0.6,
                        label="Original graph polynomial" if piece is t["pieces"][0] else None,
                    )
                for j, color in zip(candidates, ["tab:orange", "tab:purple"], strict=True):
                    intercept, design, _ = transfer_design(p, t, j, x)
                    predicted = intercept + design @ result["coefficient"]
                    alias = int(np.rint(np.mean(predicted - values) / (1 / 4.4e-6)))
                    raw = values + alias / (4.4e-6) - predicted
                    constant = float(raw.mean())
                    residual = raw - constant
                    axes[0, col].plot(
                        times,
                        predicted + constant - alias / (4.4e-6),
                        "--",
                        color=color,
                        label=f"{int(scan.norads[j])} + free constant",
                    )
                    axes[1, col].plot(
                        times, residual, ".-", color=color, label=str(int(scan.norads[j]))
                    )
                    axes[1, col].scatter(
                        times[matched], residual[matched], s=35, facecolors="none", edgecolors="red"
                    )
                    summary.append(
                        dict(
                            component=key,
                            norad=int(scan.norads[j]),
                            points=len(values),
                            timing_linked_points=int(matched.sum()),
                            free_constant_hz=constant,
                            all_rms_hz=float(np.sqrt(np.mean(residual**2))),
                            linked_rms_hz=float(np.sqrt(np.mean(residual[matched] ** 2)))
                            if matched.any()
                            else None,
                            other_rms_hz=float(np.sqrt(np.mean(residual[~matched] ** 2)))
                            if (~matched).any()
                            else None,
                            matched_time_span_s=[
                                float(times[matched].min()),
                                float(times[matched].max()),
                            ]
                            if matched.any()
                            else None,
                        )
                    )
                axes[0, col].set_title(key)
                axes[0, col].set_ylabel("Native GLRT CFO (Hz)")
                axes[1, col].axhline(0, color="black", linewidth=0.7)
                axes[1, col].set_ylabel("Residual after diagnostic free constant (Hz)")
                for ax in axes[:, col]:
                    ax.set_xlabel("Time into scan (seconds)")
                    ax.legend(fontsize=7)
            fig.suptitle(
                "Blind calibration and existing shared satellite phases; free constants are diagnostic only"
            )
            fig.tight_layout()
            fig.savefig(directory / f"conflict_{edge_index}.png", dpi=150, bbox_inches="tight")
            plt.close(fig)
        write(
            directory / "subset_diagnostics.json",
            dict(
                no_GPS_in_plot=True,
                shared_satellite_phases_and_radio_held_at_blind_parent=True,
                per_track_constants_only_diagnostic_not_association_or_calibration=True,
                records=summary,
            ),
        )


if __name__ == "__main__":
    run()
