#!/usr/bin/env python3
"""Replay and plot paired, unsmoothed GLRT probes on the three highlighted arcs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_glrt_rms import fit, write_json
from replay_scan_glrt_hyperparameters import support_center
from replay_scan_glrt_search import alias_difference

from leo.analysis.starlink.pilot_methods import refine_glrt64_epoch
from leo.storage.persistent_hop import PersistentHopIqStore, PersistentHopStoredCi16Reader


def selected_episodes(source):
    selected = json.loads((source / "orbit-summary.json").read_text())["figure_hypotheses"]
    result = []
    for item in selected:
        sid = item["session_id"]
        evidence = json.loads((source / "evidence" / f"{sid}.json").read_text())
        episodes = json.loads((source / "orbit-results" / f"{sid}.json").read_text())["episodes"]
        episode = next(e for e in episodes if e["episode_id"] == item["episode_id"])
        result.append((evidence, episode))
    return result


def replay(source, output):
    store = PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    for evidence, episode in selected_episodes(source):
        sid = evidence["inventory"]["session_id"]
        dest = output / "probes" / f"{sid}.json"
        if dest.exists():
            print(f"cached {sid}", flush=True)
            continue
        capture = store.inspect(sid)
        reader = PersistentHopStoredCi16Reader(store, capture)
        fs = evidence["inventory"]["sample_rate_hz"]
        starts, cursor = {}, 0
        for visit in capture.manifest.receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        rows, lane_metadata = [], []
        for member in episode["members"]:
            lane = next(s for s in evidence["series"] if s["tracklet_id"] == member)
            lane_metadata.append(
                {
                    "tracklet_id": member,
                    "channel": lane["channel"],
                    "edge": lane["edge"],
                    "receiver": lane["receiver"],
                }
            )
            for index, obs in enumerate(lane["observations"]):
                if obs["probe_index"] != 0:
                    raise ValueError("expected the original single-probe visit schedule")
                original = obs["persisted"]
                raw = reader.read_valid_ci16(starts[obs["visit_index"]], fs // 50)
                column = reader.receiver_ids.index(obs["receiver_id"])
                iq = raw[:, column, 0].astype(float) + 1j * raw[:, column, 1].astype(float)
                epoch = original["integer_epoch_sample"]
                for nfft in (512, 8192):
                    refined = refine_glrt64_epoch(
                        iq,
                        fs,
                        integer_epoch_sample=epoch,
                        acquired_cfo_hz=original["acquired_cfo_hz"],
                        edge=lane["edge"],
                        glrt_size=nfft,
                    )
                    row = {
                        "tracklet_id": member,
                        "index": index,
                        "candidate_id": obs["candidate_id"],
                        "visit_index": obs["visit_index"],
                        "receiver_id": obs["receiver_id"],
                        "grid_points": nfft,
                        "status": refined.status.value,
                        "probe_start_sample": original["integer_session_sample"] - epoch,
                        "probe_sample_count": fs // 50,
                        "acquired_cfo_hz": original["acquired_cfo_hz"],
                        "original_measured_cfo_hz": obs["measured_cfo_hz"],
                    }
                    fraction = refined.fractional_epoch_offset_samples
                    if fraction is not None:
                        delta = alias_difference(
                            refined.fractional_tracking_cfo_hz - obs["measured_cfo_hz"]
                        )
                        if nfft == 512 and (
                            abs(refined.fractional_tracking_cfo_hz - obs["measured_cfo_hz"]) > 1e-5
                            or abs(refined.fractional_margin - obs["margin"]) > 1e-8
                        ):
                            raise ValueError("current-grid replay differs from published probe")
                        row.update(
                            t_s=(
                                original["integer_session_sample"]
                                - epoch
                                + support_center(fs, epoch, fraction, 20)
                            )
                            / fs,
                            cfo_hz=refined.fractional_tracking_cfo_hz,
                            branch_cfo_hz=lane["y_hz"][index]
                            + delta * 11.2e9 / lane["actual_rf_hz"],
                            margin=refined.fractional_margin,
                            fractional_epoch_offset_samples=fraction,
                        )
                    rows.append(row)
        # Receiver streams may be simultaneous, but no source window is reused
        # within one receiver. The paired grid estimates intentionally share IQ.
        for receiver in {r["receiver_id"] for r in rows}:
            samples = sorted(
                r["probe_start_sample"]
                for r in rows
                if r["receiver_id"] == receiver and r["grid_points"] == 512
            )
            if len(samples) > 1 and min(np.diff(samples)) < fs // 50:
                raise ValueError("source probe windows overlap on the same receiver")
        write_json(
            dest,
            {
                "session_id": sid,
                "episode_id": episode["episode_id"],
                "candidate_name": episode["match"]["name"],
                "norad": episode["match"]["primary"]["norad"],
                "sample_rate_hz": fs,
                "lanes": lane_metadata,
                "rows": rows,
                "manifest_sha256": capture.manifest_sha256,
                "policy": (
                    "Separate per-probe GLRT and fractional timing at each grid; "
                    "same original per-probe acquisition seed; no trajectory feedback."
                ),
            },
        )
        print(f"{sid}: {len(rows) // 2} paired 20-ms probes", flush=True)


def render(output):
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10})
    summary, csv_rows = [], []
    for path in sorted((output / "probes").glob("*.json")):
        doc = json.loads(path.read_text())
        by_grid = {
            n: {
                (r["tracklet_id"], r["index"]): r
                for r in doc["rows"]
                if r["grid_points"] == n and "t_s" in r
            }
            for n in (512, 8192)
        }
        keys = sorted(set(by_grid[512]) & set(by_grid[8192]))
        t0 = min(r["t_s"] for r in by_grid[512].values())
        t = np.array([by_grid[512][k]["t_s"] for k in keys])
        y = np.array([by_grid[512][k]["branch_cfo_hz"] for k in keys])
        segment = np.array([k[0] for k in keys])
        # One shared display cubic, with one constant per original source lane.
        # Only baseline points determine it; neither estimator consumes this fit.
        baseline_trend = fit(t, y, segment, np.ones(len(t), bool), 3)
        ref = {k: float(v) for k, v in zip(keys, baseline_trend, strict=True)}
        span = max(t) - min(t)
        lanes = doc["lanes"]
        fig, axes = plt.subplots(
            len(lanes), 3, figsize=(15.5, 2.25 * len(lanes) + 1.25), squeeze=False
        )
        all_residuals = [by_grid[n][k]["branch_cfo_hz"] - ref[k] for n in (512, 8192) for k in keys]
        limit = max(100.0, np.ceil(max(abs(np.array(all_residuals))) / 50) * 50)
        for i, lane in enumerate(lanes):
            member = lane["tracklet_id"]
            selected = sorted(
                [k for k in keys if k[0] == member], key=lambda k: by_grid[512][k]["t_s"]
            )
            label = f"CH{lane['channel']} {lane['edge']} · RX{lane['receiver']}"
            combined = [
                by_grid[n][k]["branch_cfo_hz"] / 1000 for n in (512, 8192) for k in selected
            ]
            pad = max((max(combined) - min(combined)) * 0.06, 0.15)
            for col, n, color in ((0, 512, "#126a9d"), (1, 8192, "#dc721d")):
                xt = [by_grid[n][k]["t_s"] - t0 for k in selected]
                yf = [by_grid[n][k]["branch_cfo_hz"] / 1000 for k in selected]
                axes[i, col].scatter(xt, yf, s=15, color=color, alpha=0.85)
                axes[i, col].set_ylim(min(combined) - pad, max(combined) + pad)
                residual = [by_grid[n][k]["branch_cfo_hz"] - ref[k] for k in selected]
                axes[i, 2].scatter(
                    xt,
                    residual,
                    s=22 if n == 512 else 16,
                    marker="o" if n == 512 else "x",
                    facecolors="none" if n == 512 else color,
                    edgecolors=color if n == 512 else None,
                    color=None if n == 512 else color,
                    linewidths=0.85,
                    label=str(n),
                )
            axes[i, 0].set_ylabel(label + f"\nCFO (kHz) · {len(selected)} probes")
            axes[i, 2].set_ylabel("Residual (Hz)")
            axes[i, 2].set_ylim(-limit * 1.06, limit * 1.06)
            axes[i, 2].axhline(0, color="#777777", lw=0.7, alpha=0.6)
            for ax in axes[i]:
                ax.set_xlim(-1, span + 1)
                ax.grid(alpha=0.2)
                ax.ticklabel_format(axis="y", style="plain", useOffset=False)
            for k in selected:
                a, b = by_grid[512][k], by_grid[8192][k]
                csv_rows.append(
                    {
                        "session_id": doc["session_id"],
                        "candidate_name": doc["candidate_name"],
                        "tracklet_id": member,
                        "lane": label,
                        "candidate_id": a["candidate_id"],
                        "t512_s": a["t_s"],
                        "t8192_s": b["t_s"],
                        "cfo512_hz": a["branch_cfo_hz"],
                        "cfo8192_hz": b["branch_cfo_hz"],
                        "common_display_reference_hz": ref[k],
                        "difference8192_minus512_hz": b["branch_cfo_hz"] - a["branch_cfo_hz"],
                    }
                )
        axes[0, 0].set_title(
            "Current · 512 points\nIndividual 20 ms probe estimates", color="#126a9d"
        )
        axes[0, 1].set_title("8192 points\nIndividual 20 ms probe estimates", color="#bf6015")
        axes[0, 2].set_title(
            "Scatter detail · shared trend removed\nSame baseline cubic for both; not ground truth"
        )
        axes[0, 2].legend(loc="upper right", fontsize=9, ncol=2)
        for ax in axes[-1]:
            ax.set_xlabel("Seconds from trajectory start")
        fig.suptitle(
            f"{doc['candidate_name']} candidate · NORAD {doc['norad']} · {span:.1f} s\n"
            f"{len(keys)} paired probes · {doc['sample_rate_hz'] / 1e6:g} Msps · "
            f"{doc['session_id']}",
            fontsize=14,
            y=0.991,
        )
        fig.text(
            0.5,
            0.014,
            "Dots are unsmoothed estimates. Same probe IQ and acquisition seed; "
            "fractional timing refitted separately.\n"
            "CFOs use the same RF-normalized alias branch. Windows do not overlap "
            "within a receiver; satellite identity is unconfirmed.",
            ha="center",
            fontsize=9,
        )
        fig.tight_layout(rect=(0, 0.048, 1, 0.945))
        filename = f"{doc['candidate_name'].lower()}-512-vs-8192.png"
        fig.savefig(output / filename, dpi=180, facecolor="white")
        plt.close(fig)
        summary.append(
            {
                "session_id": doc["session_id"],
                "candidate_name": doc["candidate_name"],
                "span_s": span,
                "paired_probes": len(keys),
                "baseline_available": len(by_grid[512]),
                "finer_available": len(by_grid[8192]),
                "png": filename,
            }
        )
    with (output / "paired-probes.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    write_json(output / "figure-summary.json", summary)
    for row in summary:
        print(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.render_only:
        replay(args.source, args.output)
    render(args.output)


if __name__ == "__main__":
    main()
