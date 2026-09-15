#!/usr/bin/env python3
"""Reproduce the frozen eight-hour RX0 10 MS/s scanner evidence summary."""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

START = datetime(2026, 9, 14, 15, 28, tzinfo=UTC)
END = datetime(2026, 9, 14, 23, 28, tzinfo=UTC)
START_NS = int(START.timestamp() * 1e9)
END_NS = int(END.timestamp() * 1e9)
RADIO_SERIAL = "104000bac4950008230026001b440a003a"


def document(path: Path) -> dict:
    value = json.loads(path.read_text())
    return value.get("manifest", value.get("document", value))


def declared_digest(path: Path) -> str | None:
    return json.loads(path.read_text()).get("sha256")


def utc(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat().replace("+00:00", "Z")


def percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def bootstrap(values: list[float], statistic=np.median, seed: int = 20260914) -> list[float | None]:
    if not values:
        return [None, None]
    rng = random.Random(seed)
    draws = []
    for _ in range(5000):
        sample = [values[rng.randrange(len(values))] for _ in values]
        draws.append(float(statistic(sample)))
    return [percentile(draws, 2.5), percentile(draws, 97.5)]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    capture_root = Path("/srv/bulk/leo/scanner-adaptive-recordings")
    tracking_root = Path("/srv/bulk/leo/scanner-shared-tracking-v2")
    refinement_root = Path("/srv/bulk/leo/scanner-refinement-comparisons")
    analysis_root = Path("/srv/bulk/leo/scanner-adaptive-analysis")
    source_manifests: list[dict] = []

    captures: list[dict] = []
    manifests: dict[str, dict] = {}
    for path in capture_root.glob("*/manifest.json"):
        item = document(path)
        timing = item.get("timing") or {}
        start_ns = timing.get("first_sample_estimate_utc_ns")
        if not isinstance(start_ns, int) or not START_NS <= start_ns < END_NS:
            continue
        receipt = item["receipt"]
        geometry = receipt["plan"]["geometry"]
        decisions = receipt.get("host_decisions", [])
        detections = sum(d.get("feedback_outcome") == "detected" for d in decisions)
        healthy = sum(d.get("health") == "healthy" for d in decisions)
        margins = [d["numerics"]["margin"] for d in decisions if d.get("numerics")]
        row = {
            "session_id": item["session_id"],
            "capture_start_utc": utc(start_ns),
            "sample_rate_hz": geometry["sample_rate_hz"],
            "receiver_ids": ",".join(map(str, geometry["receiver_ids"])),
            "classification_receiver": receipt["plan"]["classification_receiver"],
            "radio_serial": receipt["radio_serial"],
            "valid_duty_percent": receipt["valid_duty_ppm"] / 10_000,
            "valid_seconds": receipt["valid_sample_count"] / geometry["sample_rate_hz"],
            "complete_visits": receipt["complete_visit_count"],
            "online_detections": detections,
            "online_detection_fraction": detections / len(decisions) if decisions else 0,
            "healthy_decisions": healthy,
            "median_online_margin": float(np.median(margins)) if margins else None,
            "utc_qualified": timing.get("qualified", False),
            "utc_bracket_width_ms": timing.get("first_sample_bracket_width_ns", 0) / 1e6,
            "compressed_gib": item["compressed_bytes"] / 2**30,
            "queue_high_water_visits": item.get("queue_telemetry", {}).get("high_water_visits"),
            "queue_enqueue_failures": item.get("queue_telemetry", {}).get("enqueue_failure_count"),
        }
        captures.append(row)
        manifests[item["session_id"]] = item
        source_manifests.append(
            {
                "session_id": item["session_id"],
                "product": "capture",
                "path": str(path),
                "declared_document_sha256": declared_digest(path),
            }
        )
    captures.sort(key=lambda row: row["capture_start_utc"])

    for row in captures:
        if (
            row["sample_rate_hz"] != 10_000_000
            or row["receiver_ids"] != "0"
            or row["classification_receiver"] != 0
            or row["radio_serial"] != RADIO_SERIAL
        ):
            raise RuntimeError(f"mixed acquisition cohort: {row['session_id']}")

    tracklets: list[dict] = []
    tracking_sessions: list[dict] = []
    tle_candidates: list[dict] = []
    for row in captures:
        path = tracking_root / row["session_id"] / "manifest.json"
        if not path.exists():
            continue
        item = document(path)
        source_manifests.append(
            {
                "session_id": row["session_id"],
                "product": "tracking",
                "path": str(path),
                "declared_document_sha256": declared_digest(path),
            }
        )
        local = []
        for track in item.get("tracklets", []):
            value = {
                "session_id": row["session_id"],
                "capture_start_utc": row["capture_start_utc"],
                "channel": track["channel"],
                "edge": track["edge"],
                "receiver_id": track["receiver_id"],
                "observation_count": track["observation_count"],
                "support_span_s": (track["end_utc_ns"] - track["start_utc_ns"]) / 1e9,
                "normalized_rate_hz_per_s": track["normalized_rate_hz_per_s"],
                "linear_fit_residual_rms_hz": track["residual_rms_hz"],
            }
            tracklets.append(value)
            local.append(value)
        weights = sum(x["observation_count"] for x in local)
        pooled = (
            math.sqrt(
                sum(x["observation_count"] * x["linear_fit_residual_rms_hz"] ** 2 for x in local)
                / weights
            )
            if weights
            else None
        )
        snap = item.get("eligible_tle_snapshot")
        capture_ns = manifests[row["session_id"]]["timing"]["first_sample_estimate_utc_ns"]
        tracking_sessions.append(
            {
                "session_id": row["session_id"],
                "tracklet_count": len(local),
                "observation_count": weights,
                "pooled_linear_fit_residual_rms_hz": pooled,
                "median_tracklet_residual_rms_hz": float(
                    np.median([x["linear_fit_residual_rms_hz"] for x in local])
                )
                if local
                else None,
                "trajectory_state": item["trajectory_state"],
                "trajectory_time_basis": item.get("trajectory_time_basis"),
                "tle_state": item["tle_state"],
                "physical_group_count": item["physical_group_count"],
                "eligible_group_count": item["eligible_group_count"],
                "attempted_group_count": item["attempted_group_count"],
                "deferred_group_count": item["deferred_group_count"],
                "projected_candidate_count": item["projected_candidate_count"],
                "tle_candidate_count": len(item.get("tle_candidates", [])),
                "tle_snapshot_age_minutes": (capture_ns - snap["collected_utc_ns"]) / 60e9
                if snap
                else None,
                "tle_snapshot_object_count": snap["object_count"] if snap else None,
                "unscored_reasons": " | ".join(
                    sorted({x["reason"] for x in item.get("unscored_groups", [])})
                ),
            }
        )
        for candidate in item.get("tle_candidates", []):
            tle_candidates.append(
                {
                    "session_id": row["session_id"],
                    "capture_start_utc": row["capture_start_utc"],
                    "leading_catalog_number": candidate["leading_catalog_number"],
                    "support_span_s": candidate["support_span_s"],
                    "scored_observation_count": candidate["scored_observation_count"],
                    "nominal_candidate_count": candidate["nominal_candidate_count"],
                    "training_leader_heldout_rank": candidate["training_leader_heldout_rank"],
                    "heldout_runner_negative_log_score_margin": candidate[
                        "heldout_runner_negative_log_score_margin"
                    ],
                    "nominal_heldout_negative_log_score": candidate[
                        "nominal_heldout_negative_log_score"
                    ],
                    "radio_null_heldout_negative_log_score": candidate[
                        "radio_null_heldout_negative_log_score"
                    ],
                    "wrong_time_minus_500_heldout_negative_log_score": candidate[
                        "wrong_time_minus_500_heldout_negative_log_score"
                    ],
                    "wrong_time_plus_500_heldout_negative_log_score": candidate[
                        "wrong_time_plus_500_heldout_negative_log_score"
                    ],
                    "abstention_recommended": candidate["abstention_recommended"],
                    "abstention_reasons": " | ".join(candidate["abstention_reasons"]),
                    "identity_claimed": candidate["identity_claimed"],
                }
            )

    refinement_rows: list[dict] = []
    for row in captures:
        path = refinement_root / row["session_id"] / "manifest.json"
        if not path.exists():
            continue
        item = document(path)
        source_manifests.append(
            {
                "session_id": row["session_id"],
                "product": "refinement",
                "path": str(path),
                "declared_document_sha256": declared_digest(path),
            }
        )
        for metric in item["metrics"]:
            refinement_rows.append({"session_id": row["session_id"], **metric})

    png_rows = []
    for row in captures:
        sid = row["session_id"]
        bindings = [p for p in (analysis_root / sid).glob("*") if p.is_dir()]
        adaptive = (
            sum(p.name.endswith(".png") for p in bindings[0].glob("*.png")) if bindings else 0
        )
        tracking = sum(p.name.endswith(".png") for p in (tracking_root / sid).glob("*.png"))
        refinement = sum(p.name.endswith(".png") for p in (refinement_root / sid).glob("*.png"))
        png_rows.append(
            {
                "session_id": sid,
                "adaptive_pngs": adaptive,
                "tracking_pngs": tracking,
                "refinement_pngs": refinement,
                "total_pngs": adaptive + tracking + refinement,
            }
        )

    duty = [x["valid_duty_percent"] for x in captures]
    session_rms = [
        x["pooled_linear_fit_residual_rms_hz"]
        for x in tracking_sessions
        if x["pooled_linear_fit_residual_rms_hz"] is not None
    ]
    tracking_states = Counter(x["tle_state"] for x in tracking_sessions)
    reasons = Counter(x["unscored_reasons"] for x in tracking_sessions if x["unscored_reasons"])

    refinement_summary = []
    grouped = defaultdict(list)
    for row in refinement_rows:
        grouped[(row["case"], row["profile"])].append(row)
    for (case, profile), rows in sorted(grouped.items()):
        common = sum(x["common"] for x in rows)

        def pooled(name: str, rows: list[dict] = rows, common: int = common) -> float | None:
            return (
                math.sqrt(sum(x["common"] * x[name] ** 2 for x in rows) / common)
                if common
                else None
            )

        refinement_summary.append(
            {
                "case": case,
                "profile": profile,
                "sessions": len(rows),
                "attempted": sum(x["attempted"] for x in rows),
                "recovered": sum(x["recovered"] for x in rows),
                "common": common,
                "raw_cfo_rms_hz": pooled("raw_cfo_rms_hz"),
                "folded_cfo_rms_hz": pooled("cfo_rms_hz"),
                "delay_rms_ns": pooled("delay_rms_ns"),
                "alias_changes": sum(x["alias_changes"] for x in rows),
            }
        )

    summary = {
        "schema": "org.leo.research.eight-hour-scanner-summary/v1",
        "window": {
            "start_utc": START.isoformat().replace("+00:00", "Z"),
            "end_utc": END.isoformat().replace("+00:00", "Z"),
            "end_exclusive": True,
        },
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "acquisition": {
            "successful_sessions": len(captures),
            "expected_ten_minute_slots": 48,
            "failed_slots": 1,
            "radio_serial": RADIO_SERIAL,
            "sample_rate_hz": 10_000_000,
            "receiver_ids": [0],
            "duty_percent_median": float(np.median(duty)),
            "duty_percent_mean": float(np.mean(duty)),
            "duty_percent_min": min(duty),
            "duty_percent_max": max(duty),
            "duty_median_bootstrap_95_ci": bootstrap(duty),
            "total_valid_seconds": sum(x["valid_seconds"] for x in captures),
            "total_online_detections": sum(x["online_detections"] for x in captures),
            "total_complete_visits": sum(x["complete_visits"] for x in captures),
            "all_utc_qualified": all(x["utc_qualified"] for x in captures),
            "utc_bracket_width_ms_median": float(
                np.median([x["utc_bracket_width_ms"] for x in captures])
            ),
            "utc_bracket_width_ms_max": max(x["utc_bracket_width_ms"] for x in captures),
        },
        "glrt_tracking": {
            "sessions": len(tracking_sessions),
            "tracklets": len(tracklets),
            "observations": sum(x["observation_count"] for x in tracklets),
            "session_pooled_linear_fit_residual_rms_hz_median": float(np.median(session_rms))
            if session_rms
            else None,
            "session_pooled_linear_fit_residual_rms_hz_median_bootstrap_95_ci": bootstrap(
                session_rms
            ),
            "tracklet_residual_rms_hz_median": float(
                np.median([x["linear_fit_residual_rms_hz"] for x in tracklets])
            )
            if tracklets
            else None,
            "tracklet_residual_rms_hz_p10_p90": [
                percentile([x["linear_fit_residual_rms_hz"] for x in tracklets], 10),
                percentile([x["linear_fit_residual_rms_hz"] for x in tracklets], 90),
            ],
            "rate_hz_per_s_median": float(
                np.median([x["normalized_rate_hz_per_s"] for x in tracklets])
            )
            if tracklets
            else None,
        },
        "controlled_refinement": refinement_summary,
        "tle": {
            "states": dict(tracking_states),
            "completed_candidate_matches": sum(x["tle_candidate_count"] for x in tracking_sessions),
            "non_abstained_candidates": sum(
                not x["abstention_recommended"] for x in tle_candidates
            ),
            "identity_claims": sum(x["identity_claimed"] for x in tle_candidates),
            "attempted_groups": sum(x["attempted_group_count"] for x in tracking_sessions),
            "eligible_groups": sum(x["eligible_group_count"] for x in tracking_sessions),
            "projected_candidates": sum(x["projected_candidate_count"] for x in tracking_sessions),
            "unscored_reason_counts": dict(reasons),
            "snapshot_age_minutes_median": float(
                np.median(
                    [
                        x["tle_snapshot_age_minutes"]
                        for x in tracking_sessions
                        if x["tle_snapshot_age_minutes"] is not None
                    ]
                )
            )
            if tracking_sessions
            else None,
        },
        "pss": {
            "current_window_observations": 0,
            "reason": (
                "The production adaptive profile published edge-pilot GLRT products "
                "only; no PSS product was scheduled or persisted."
            ),
        },
        "presentation": {
            "sessions_with_7_of_7_pngs": sum(x["total_pngs"] == 7 for x in png_rows),
            "sessions_incomplete_at_generation": [
                x["session_id"] for x in png_rows if x["total_pngs"] < 7
            ],
        },
    }

    write_csv(output / "sessions.csv", captures)
    write_csv(output / "tracking-sessions.csv", tracking_sessions)
    write_csv(output / "tracklets.csv", tracklets)
    write_csv(output / "tle-candidates.csv", tle_candidates)
    write_csv(output / "refinement-metrics.csv", refinement_rows)
    write_csv(output / "png-inventory.csv", png_rows)
    write_csv(output / "source-manifests.csv", source_manifests)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    times = [
        datetime.fromisoformat(x["capture_start_utc"].replace("Z", "+00:00")) for x in captures
    ]
    fig, ax1 = plt.subplots(figsize=(12, 5.5))
    ax1.plot(times, duty, "o-", color="#1676a3", label="source-counter duty")
    ax1.set_ylabel("Valid capture duty (%)")
    ax1.set_ylim(90, 100)
    ax1.grid(alpha=0.25)
    ax2 = ax1.twinx()
    ax2.bar(
        times,
        [x["online_detections"] for x in captures],
        width=0.004,
        alpha=0.35,
        color="#cf4d61",
        label="online detected visits",
    )
    ax2.set_ylabel("Online detected visits per 300 s scan")
    ax1.set_title("Frozen eight-hour RX0 10 MS/s scanner cohort")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output / "capture-duty-and-detections.png", dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    for channel in range(1, 5):
        rows = [x for x in tracklets if x["channel"] == channel]
        ax.scatter(
            [x["normalized_rate_hz_per_s"] for x in rows],
            [x["linear_fit_residual_rms_hz"] for x in rows],
            s=12,
            alpha=0.45,
            label=f"CH{channel}",
        )
    ax.set_yscale("log")
    ax.set_xlabel("Local normalized CFO rate (Hz/s)")
    ax.set_ylabel("Residual RMS after local linear fit (Hz)")
    ax.set_title("GLRT tracklet carrier-rate evidence; each point is one local association")
    ax.grid(alpha=0.25)
    ax.legend(ncol=4)
    fig.tight_layout()
    fig.savefig(output / "glrt-tracklet-rate-residuals.png", dpi=170)
    plt.close(fig)

    frequency = [x for x in refinement_summary if x["case"] == "frequency"]
    delay = [x for x in refinement_summary if x["case"] == "delay"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].bar(
        [x["profile"] for x in frequency],
        [x["folded_cfo_rms_hz"] for x in frequency],
        color="#1676a3",
    )
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Injected-frequency recovery RMS (Hz)")
    axes[0].tick_params(axis="x", rotation=25)
    axes[1].bar([x["profile"] for x in delay], [x["delay_rms_ns"] for x in delay], color="#cf4d61")
    axes[1].set_ylabel("Injected-delay recovery RMS (ns)")
    axes[1].tick_params(axis="x", rotation=25)
    fig.suptitle("Controlled 10 MS/s refinement checks; pooled over common recovered probes")
    fig.tight_layout()
    fig.savefig(output / "controlled-refinement-rms.png", dpi=170)
    plt.close(fig)

    labels = [
        "PSS 25M\ncausal accepted",
        "GLRT 25M\nfractional",
        "GLRT derived 2.5M\nfractional",
        "GLRT other 2.5M\nfractional",
    ]
    historical = [
        [3.18, 4.64, 3.18, 5.12, 3.83],
        [10.53, 11.46, 11.94, 11.43, 11.54],
        [26.27, 21.91, 21.34, 21.94, 21.50],
        [33.02, 29.46, 23.50, 21.02, 21.21],
    ]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.boxplot(historical, tick_labels=labels, showmeans=True)
    ax.set_ylabel("Alternating-fit timing residual RMS (ns)")
    ax.set_title("Historical five-dwell comparator (unmatched to the eight-hour scanner cohort)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output / "historical-pss-glrt-timing-comparison.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
