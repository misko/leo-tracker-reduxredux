"""Trace the graph origin and independently fit three fixed 20-second windows."""

import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from diagnose_s01_ch2_t000 import OUTPUT, TARGET
from inventory_clipped_phase_cohort import ROOT

from leo.analysis import graph_tracklets, tracklet_fitting
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.analysis.research.robust_polynomial_order import polynomial_orders

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DESTINATION = OUTPUT / "segments_20s"
PERIOD = 1 / 4.4e-6


def evaluate(fit, times, derivative=0):
    coefficients = np.polynomial.polynomial.polyder(fit["coefficients_hz"], derivative)
    x = (np.asarray(times) - fit["reference_time_s"]) / fit["time_scale_s"]
    return np.polynomial.polynomial.polyval(x, coefficients) / fit["time_scale_s"] ** derivative


def trace_graph(target):
    base = ROOT / "reports/2026_10_17_dsx01_all_scans_tracklets/graph/S01"
    summary = json.loads((base / "primary/results.json").read_text())
    with (base / "primary/assignments.csv").open() as stream:
        rows = [
            r for r in csv.DictReader(stream) if (int(r["receiver"]), int(r["channel"])) == (1, 2)
        ]
    times = np.array([float(r["time_s"]) for r in rows])
    values = np.array([float(r["measured_cfo_hz"]) for r in rows])
    ids = np.array([r["observation_id"] for r in rows])
    assert {r["observation_id"] for r in rows if int(r["track_id"]) == 0} == set(
        target["observation_ids"]
    )
    order = np.lexsort((values, times))
    wanted = set(np.flatnonzero(np.isin(ids[order], target["observation_ids"])).tolist())
    events = []
    original_finish, original_repair = (
        graph_tracklets.finish_lane,
        tracklet_fitting._repair_structured,
    )

    def record_finish(t, y, sorted_order, n_original, models, cfg, method, diagnostics=None):
        events.append(
            dict(
                stage="graph_proposals_before_finalization",
                models=[
                    dict(
                        points=len(m["indices"]),
                        exact_target=set(m["indices"].tolist()) == wanted,
                        target_overlap=len(set(m["indices"].tolist()) & wanted),
                    )
                    for m in models
                ],
            )
        )
        return original_finish(t, y, sorted_order, n_original, models, cfg, method, diagnostics)

    def record_repair(models, t, y, cfg):
        before = [set(m["indices"].tolist()) for m in models]
        result = original_repair(models, t, y, cfg)
        for group in result:
            members = set(np.concatenate([p["indices"] for p in group]).tolist())
            if members == wanted:
                events.append(
                    dict(
                        stage="structured_repair_target",
                        output_pieces=len(group),
                        exact_target_present_before_repair=any(x == wanted for x in before),
                        contributing_input_models=[
                            dict(points=len(x), target_overlap=len(x & wanted))
                            for x in before
                            if x & wanted
                        ],
                    )
                )
        return result

    hashes = {
        name: "sha256:" + hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
        for name, expected in summary["provenance"]["source_hashes"].items()
        if name.startswith("src/")
    }
    assert all(hashes.values()), "scientific graph source differs from recorded provenance"
    try:
        graph_tracklets.finish_lane = record_finish
        tracklet_fitting._repair_structured = record_repair
        replay = graph_tracklets.fit_lane(times, values, TrackConfig(**summary["config"]))
    finally:
        graph_tracklets.finish_lane = original_finish
        tracklet_fitting._repair_structured = original_repair
    own = [t for t in replay["tracks"] if set(ids[t["indices"]]) == set(target["observation_ids"])]
    assert len(own) == 1
    with (base / "recovered/assignments.csv").open() as stream:
        recovered_ids = [
            r["observation_id"]
            for r in csv.DictReader(stream)
            if (int(r["receiver"]), int(r["channel"]), int(r["track_id"])) == (1, 2, 0)
        ]
    assert set(recovered_ids) == set(target["observation_ids"])
    return dict(
        source_hashes_match=hashes,
        replay_exact_membership=True,
        events=events,
        primary_recovered_robust_membership_identical=True,
        final_piece_count=len(own[0]["pieces"]),
        rows=rows,
    )


def run():
    DESTINATION.mkdir(exist_ok=True)
    target = json.loads((OUTPUT / "target.json").read_text())
    times, values = np.array(target["times"]), np.array(target["values"])
    trace = trace_graph(target)
    rows = trace.pop("rows")
    lookup = {r["observation_id"]: r for r in rows}
    native = np.array([float(lookup[oid]["measured_cfo_hz"]) for oid in target["observation_ids"]])
    lifts = np.rint((values - native) / PERIOD).astype(int)
    np.testing.assert_allclose(values, native + lifts * PERIOD, atol=1e-7)
    full = json.loads((OUTPUT / "polynomial_orders.json").read_text())[0]
    allfits, membership = [], []
    for lo in (240, 260, 280):
        hi = lo + 20
        mask = (times >= lo) & (times < hi)
        t, y = times[mask], values[mask]
        fits = polynomial_orders(t, y)
        fit = fits[0]
        assert all(fit["inlier_mask"])
        membership.extend(np.array(target["observation_ids"])[mask].tolist())
        record = dict(
            start_s=lo,
            end_s=hi,
            points=int(mask.sum()),
            best=fit,
            all_orders=fits,
            global_quartic_rms_hz=float(np.sqrt(np.mean((y - evaluate(full, t)) ** 2))),
            observation_ids=np.array(target["observation_ids"])[mask].tolist(),
            alias_lifts=lifts[mask],
            maximum_adjacent_gap_s=float(np.max(np.diff(t))),
        )
        allfits.append(record)
        grid = np.linspace(lo, hi, 500)
        full_curve, local_curve = evaluate(full, grid), evaluate(fit, grid)
        local_full, local_pred = evaluate(full, t), evaluate(fit, t)
        dominant = int(np.median(lifts[mask]))
        midpoint = (lo + hi) / 2
        tangent = evaluate(full, midpoint) + evaluate(full, midpoint, 1) * (grid - midpoint)
        tangent_t = evaluate(full, midpoint) + evaluate(full, midpoint, 1) * (t - midpoint)
        background = [
            r
            for r in rows
            if lo <= float(r["time_s"]) < hi
            and r["observation_id"] not in target["observation_ids"]
        ]
        fig, axes = plt.subplots(
            3,
            1,
            figsize=(12, 9),
            sharex=True,
            layout="constrained",
            gridspec_kw=dict(height_ratios=[1.2, 1, 1]),
        )
        if background:
            axes[0].scatter(
                [float(r["time_s"]) for r in background],
                [float(r["measured_cfo_hz"]) / 1000 for r in background],
                color="lightgray",
                marker="x",
                label="Other RX1 CH2 GLRT",
            )
        axes[0].scatter(
            t, native[mask] / 1000, color="black", s=24, label="Target GLRT, native CFO"
        )
        axes[0].plot(
            grid,
            (full_curve - dominant * PERIOD) / 1000,
            color="darkorange",
            lw=2,
            label=f"Full-track polynomial, degree {full['degree']}",
        )
        axes[0].plot(
            grid,
            (local_curve - dominant * PERIOD) / 1000,
            color="seagreen",
            ls="--",
            lw=2,
            label=f"Independent segment fit, degree {fit['degree']}",
        )
        odd = lifts[mask] != dominant
        if odd.any():
            for ti, yi in zip(t[odd], native[mask][odd], strict=True):
                axes[0].annotate(
                    "Native alias branch; corrected in panels below",
                    (ti, yi / 1000),
                    xytext=(lo + 1, yi / 1000 + 15),
                    fontsize=8,
                    color="purple",
                    arrowprops=dict(arrowstyle="->", color="purple"),
                )
        axes[0].set(ylabel="Native GLRT CFO (kHz)")
        axes[1].scatter(
            t,
            y - tangent_t,
            color="black",
            s=24,
            label="GLRT, original alias lifts; common tangent removed",
        )
        axes[1].plot(
            grid, full_curve - tangent, color="darkorange", lw=2, label="Full-track polynomial"
        )
        axes[1].plot(
            grid,
            local_curve - tangent,
            color="seagreen",
            ls="--",
            lw=2,
            label="Independent segment fit",
        )
        axes[1].set(
            ylabel="CFO minus common straight line (Hz)",
            title="Curvature enlarged; same straight line removed from points and both fits",
        )
        axes[2].plot(
            t,
            y - local_full,
            "o-",
            ms=3,
            color="darkorange",
            label=f"Residual to full polynomial: {record['global_quartic_rms_hz']:.1f} Hz RMS",
        )
        axes[2].plot(
            t,
            y - local_pred,
            "o-",
            ms=3,
            color="seagreen",
            label=f"Residual to independent fit: {fit['full_rms_hz']:.1f} Hz RMS",
        )
        axes[2].axhline(0, color="black", lw=0.7)
        axes[2].set(ylabel="Residual (Hz)", xlabel="Seconds from S01 start")
        for ax in axes:
            ax.set_xlim(lo, hi)
            ax.grid(alpha=0.2)
            ax.legend(fontsize=7, loc="best")
        fig.suptitle(
            f"S01 RX1 CH2 T000 — {lo}–{hi} s, {mask.sum()} GLRT points\n"
            "Independent degree 1–4 comparison; all points retained; no satellite used"
        )
        fig.savefig(DESTINATION / f"segment_{lo}_{hi}.png", dpi=170)
        plt.close(fig)
    assert membership == target["observation_ids"]
    seams = []
    for left, right in zip(allfits[:-1], allfits[1:], strict=True):
        boundary = left["end_s"]
        seams.append(
            dict(
                boundary_s=boundary,
                independent_prediction_difference_hz=float(
                    evaluate(right["best"], boundary) - evaluate(left["best"], boundary)
                ),
                independent_slope_difference_hz_s=float(
                    evaluate(right["best"], boundary, 1) - evaluate(left["best"], boundary, 1)
                ),
                warning="independent fits extrapolated slightly into the sampling gap",
            )
        )
        nominal_variance = 0.0
        for segment in (left, right):
            fit = segment["best"]
            own_times = times[(times >= segment["start_s"]) & (times < segment["end_s"])]
            x = (own_times - fit["reference_time_s"]) / fit["time_scale_s"]
            design = np.polynomial.polynomial.polyvander(x, fit["degree"])
            at_boundary = np.polynomial.polynomial.polyvander(
                (boundary - fit["reference_time_s"]) / fit["time_scale_s"], fit["degree"]
            )[0]
            nominal_variance += (
                float(at_boundary @ np.linalg.inv(design.T @ design) @ at_boundary) * 150**2
            )
        seams[-1]["nominal_independent_150hz_boundary_difference_sigma_hz"] = float(
            np.sqrt(nominal_variance)
        )
        seams[-1]["caution"] = (
            "conditional independent-noise uncertainty; shared RX fluctuations omitted"
        )
    nonmembers = [
        r
        for r in rows
        if r["observation_id"] not in target["observation_ids"]
        and times[0] <= float(r["time_s"]) <= times[-1]
    ]
    distances = []
    for row in nonmembers:
        predicted = evaluate(full, float(row["time_s"]))
        delta = float(row["measured_cfo_hz"]) - predicted
        delta -= round(delta / PERIOD) * PERIOD
        distances.append(abs(float(delta)))
    result = dict(
        target=TARGET,
        graph_trace=trace,
        segments=allfits,
        seams=seams,
        full_track_score=full["score"],
        independent_segment_score_sum=sum(r["best"]["score"] for r in allfits),
        split_penalty_not_yet_added=True,
        all_80_observations_preserved=True,
        maximum_observed_gap_s=float(np.max(np.diff(times))),
        other_same_lane_glrt_points_in_interval=len(nonmembers),
        minimum_alias_aware_distance_of_nonmember_to_full_polynomial_hz=min(distances)
        if distances
        else None,
        alias_exceptions=[
            dict(time_s=float(t), native_cfo_hz=float(y), alias_lift=int(lift))
            for t, y, lift in zip(times, native, lifts, strict=True)
            if lift != int(np.median(lifts))
        ],
    )
    write(DESTINATION / "results.json", result)
    print(
        json.dumps(
            dict(
                graph_trace=trace,
                segments=[
                    dict(
                        start_s=r["start_s"],
                        points=r["points"],
                        degree=r["best"]["degree"],
                        rms_hz=r["best"]["full_rms_hz"],
                        score=r["best"]["score"],
                    )
                    for r in allfits
                ],
                seams=seams,
                full_score=full["score"],
                split_score=result["independent_segment_score_sum"],
                max_gap=result["maximum_observed_gap_s"],
                alias_exceptions=result["alias_exceptions"],
            )
        )
    )


if __name__ == "__main__":
    run()
