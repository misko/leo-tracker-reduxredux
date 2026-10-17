"""Audit leftovers and append bounded residual fits without changing prior memberships."""

from __future__ import annotations

import copy
import csv
import importlib
import json
from dataclasses import replace

import numpy as np
from compare_tracklet_methods import METHODS, assert_integrity
from evaluate_polynomial_tracklets import (
    DEFAULT_INPUT,
    REPO,
    digest,
    evaluate_lanes,
    load_observations,
    save_results,
)
from render_full_data_tracklet_review import LABELS, load_selected
from tune_full_data_tracklets import (
    annotate_full_data_quality,
    audit_real_result,
    full_residual_diagnostics,
)

from leo.analysis.polynomial_tracklets import TrackConfig, _predict
from leo.analysis.residual_tracklets import fit_lane as quadratic_fit

OUTPUT = REPO / "reports/2026_10_17_dsx01_residual_review"


def append_recovery(base, t, y, cfg, fitter, stage):
    """Keep every existing track unchanged; append only non-flagged residual proposals."""
    result = copy.deepcopy(base)
    unresolved = np.flatnonzero(np.asarray(result["assignment"]) < 0)
    rescue = fitter(t[unresolved], y[unresolved], cfg)
    assert_integrity(rescue, t[unresolved], y[unresolved], cfg)
    rejected = []
    for track in rescue["tracks"]:
        flags = []
        for piece in track["pieces"]:
            ix = np.asarray(piece["indices"], int)
            residual = (
                y[unresolved[ix]]
                + rescue["alias_lifts"][ix] * cfg.alias_spacing_hz
                - _predict(piece, t[unresolved[ix]])
            )
            quality = full_residual_diagnostics(t[unresolved[ix]], residual, cfg.noise_sigma_hz)
            flags.extend(quality["flags"])
        if flags:
            rejected.append({"points": len(track["indices"]), "flags": sorted(set(flags))})
            continue
        track = copy.deepcopy(track)
        local = np.asarray(track["indices"], int)
        track["indices"] = unresolved[local]
        for piece in track["pieces"]:
            piece["indices"] = unresolved[np.asarray(piece["indices"], int)]
        track["recovery_stage"] = stage
        result["assignment"][unresolved[local]] = len(result["tracks"])
        result["alias_lifts"][unresolved[local]] = rescue["alias_lifts"][local]
        result["tracks"].append(track)
    result.setdefault("diagnostics", {}).setdefault("recovery", []).append(
        {
            "stage": stage,
            "starting_unresolved": len(unresolved),
            "added": int(
                np.sum(np.asarray(base["assignment"]) < 0)
                - np.sum(np.asarray(result["assignment"]) < 0)
            ),
            "rejected_structured_candidates": rejected,
            "search_diagnostics": rescue.get("diagnostics", {}),
        }
    )
    return result


def replay_fitter(summary, exports, original_cfg, original_fitter, relaxed):
    cursor = iter(summary["lanes"])

    def fit(t, y, config):
        lane = next(cursor)
        group = [
            r
            for r in exports
            if (r["receiver"], r["channel"]) == (lane["receiver"], lane["channel"])
        ]
        np.testing.assert_array_equal(t, [r["time_s"] for r in group])
        np.testing.assert_array_equal(y, [r["measured_cfo_hz"] for r in group])
        base = {
            "tracks": copy.deepcopy(lane["tracks"]),
            "assignment": np.array([r["track_id"] for r in group]),
            "alias_lifts": np.array([r["alias_lift"] for r in group]),
            "diagnostics": {"original_method": summary.get("method")},
        }
        result = append_recovery(base, t, y, original_cfg, original_fitter, "same_method")
        result = append_recovery(result, t, y, original_cfg, quadratic_fit, "quadratic_strict")
        if relaxed:
            result = append_recovery(result, t, y, config, quadratic_fit, "quadratic_support2")
        assert_integrity(result, t, y, config)
        prior = base["assignment"] >= 0
        np.testing.assert_array_equal(result["assignment"][prior], base["assignment"][prior])
        np.testing.assert_array_equal(result["alias_lifts"][prior], base["alias_lifts"][prior])
        return result

    return fit


def plot_recovery(method, original, summary, exports):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    original_ids = {r["observation_id"] for r in original if r["track_id"] < 0}
    fig, axes = plt.subplots(8, 2, figsize=(16, 22), sharex=True)
    colors = {
        "same_method": "#437fba",
        "quadratic_strict": "#248668",
        "quadratic_support2": "#cf6c24",
    }
    for lane in summary["lanes"]:
        rx, ch = lane["receiver"], lane["channel"]
        ax = axes[ch - 1, rx - 1]
        group = [
            r
            for r in exports
            if (r["receiver"], r["channel"]) == (rx, ch) and r["observation_id"] in original_ids
        ]
        remaining = [r for r in group if r["track_id"] < 0]
        ax.scatter(
            [r["time_s"] for r in remaining],
            [r["measured_cfo_hz"] / 1000 for r in remaining],
            color="#a0a6ac",
            s=14,
        )
        for tid, track in enumerate(lane["tracks"]):
            if "recovery_stage" not in track:
                continue
            color = colors[track["recovery_stage"]]
            points = [r for r in group if r["track_id"] == tid]
            ax.scatter(
                [r["time_s"] for r in points],
                [r["measured_cfo_hz"] / 1000 for r in points],
                color=color,
                s=18,
            )
            for pid, piece in enumerate(track["pieces"]):
                members = sorted(
                    (r for r in points if r["piece_id"] == pid), key=lambda r: r["time_s"]
                )
                for left, right in zip(members[:-1], members[1:], strict=True):
                    if left["alias_lift"] != right["alias_lift"]:
                        continue
                    time = np.linspace(left["time_s"], right["time_s"], 12)
                    prediction = (
                        _predict(piece, time)
                        - left["alias_lift"] * summary["config"]["alias_spacing_hz"]
                    )
                    ax.plot(time, prediction / 1000, color=color, linewidth=0.8)
            mid = points[len(points) // 2]
            ax.annotate(
                f"{len(points)}pt/d{max(p['degree'] for p in track['pieces'])}",
                (mid["time_s"], mid["measured_cfo_hz"] / 1000),
                xytext=(3, 4),
                textcoords="offset points",
                fontsize=7,
                color=color,
            )
        ax.set_title(
            f"RX{rx} CH{ch} · {len(group) - len(remaining)} recovered / "
            f"{len(group)} prior leftovers",
            loc="left",
            fontsize=10,
        )
        ax.set_xlim(0, 300)
        ax.grid(alpha=0.18)
    fig.suptitle(
        f"DSX01 S01 · {LABELS[method]} · Review of previously unassociated GLRT points\n"
        "Blue: same-method rerun · Green: quadratic seeds, original support · "
        "Orange: two points/coefficient · Gray: remaining",
        fontsize=14,
        y=0.995,
    )
    fig.supxlabel("Time since first-sample estimate (s)")
    fig.supylabel("Measured GLRT CFO (kHz)")
    fig.text(
        0.5,
        0.025,
        "Only prior leftovers shown. Short recovered fits remain provisional; "
        "existing associations were frozen.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.025, 0.035, 1, 0.96))
    directory = OUTPUT / method
    for extension in ("png", "pdf"):
        fig.savefig(directory / f"recovered-leftovers.{extension}", dpi=140)
    plt.close(fig)


def main():
    rows, provenance = load_observations(DEFAULT_INPUT)
    records = []
    hashes = {
        str(p.relative_to(REPO)): digest(p)
        for p in (
            REPO / "src/leo/analysis/residual_tracklets.py",
            REPO / "tools/review_unassociated_tracklets.py",
        )
    }
    for method in LABELS:
        selected, original_summary, original_exports = load_selected(method)
        cfg = TrackConfig(**selected["config"])
        fitter = importlib.import_module(METHODS[method]).fit_lane
        summaries = {}
        for policy in ("strict", "support2"):
            current_cfg = cfg if policy == "strict" else replace(cfg, points_per_coefficient=2)
            runner = replay_fitter(
                original_summary, original_exports, cfg, fitter, policy == "support2"
            )
            summary, exports = evaluate_lanes(rows, current_cfg, runner)
            annotate_full_data_quality(summary, exports)
            audit_real_result(rows, summary, exports, current_cfg)
            summary["provenance"] = {
                **provenance,
                "recovery_source_hashes": hashes,
                "original_selected_trial": selected["name"],
            }
            summary["method"] = method
            summary["recovery_policy"] = (
                "Append only. Existing memberships and coefficients frozen. "
            )
            summary["recovery_policy"] += (
                "No new track with detected full-data residual structure accepted."
            )
            summaries[policy] = (summary, exports)
            save_results(OUTPUT / method / policy, summary, exports)
            original_by_id = {r["observation_id"]: r for r in original_exports}
            new_rows = [
                r
                for r in exports
                if r["track_id"] >= 0 and original_by_id[r["observation_id"]]["track_id"] < 0
            ]
            stages = {}
            for lane in summary["lanes"]:
                for track in lane["tracks"]:
                    stage = track.get("recovery_stage")
                    if stage:
                        stages[stage] = stages.get(stage, 0) + len(track["indices"])
            record = {
                "method": method,
                "policy": policy,
                "original_assigned": selected["assigned"],
                "assigned": summary["assigned"],
                "new_associations": len(new_rows),
                "unassociated": summary["unresolved"],
                "tracks": summary["track_count"],
                "stages": stages,
                "residual_quality": summary["residual_quality"],
            }
            records.append(record)
            print("RECOVERY", json.dumps(record), flush=True)
        strict_assigned = {
            r["observation_id"] for r in summaries["strict"][1] if r["track_id"] >= 0
        }
        relaxed_assigned = {
            r["observation_id"] for r in summaries["support2"][1] if r["track_id"] >= 0
        }
        assert strict_assigned <= relaxed_assigned
        plot_recovery(method, original_exports, *summaries["support2"])
    (OUTPUT / "summary.json").write_text(json.dumps(records, indent=2) + "\n")
    with (OUTPUT / "comparison.csv").open("w") as stream:
        flat = [{k: v for k, v in r.items() if not isinstance(v, dict)} for r in records]
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    assert all(digest(REPO / p) == value for p, value in hashes.items())


if __name__ == "__main__":
    main()
