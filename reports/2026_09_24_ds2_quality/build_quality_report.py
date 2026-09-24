#!/usr/bin/env python3
"""Build a sealed, descriptive data-quality report for the 20-session DS2 corpus.

This is deliberately a corpus report, not a positioning program.  It reads the
frozen DS2 membership and completed V14 tracking products, and emits only
descriptive signal/track/candidate-quality summaries.  In particular, it does
not read an observer location, position diagnostic, or reference coordinate.

The default data source is the authoritative local tracking-product endpoint.
``--products`` accepts a prior sanitized snapshot so the report can be
reproduced without contacting that endpoint.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any
from urllib.request import urlopen

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE.parent / "2026_09_24_ds2_inventory" / "manifest.json"
TRACKING_API = "http://127.0.0.1:8090/api/v1/scanner/tracking"
EXPECTED_SESSIONS = 20


def canonical_digest(value: Any) -> str:
    """Return a stable digest for the report's compact source snapshot."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], p: float) -> float | None:
    """Linearly interpolated percentile with an explicit empty convention."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * p
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def distribution(values: list[float]) -> dict[str, float | int | None]:
    """Summarize a numeric quantity without assuming a normal distribution."""
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "p10": percentile(values, 0.10),
        "p25": percentile(values, 0.25),
        "median": median(values) if values else None,
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "max": max(values) if values else None,
    }


def strict_manifest(path: Path) -> list[dict[str, Any]]:
    """Load exactly the raw-eligible frozen DS2 sessions, rejecting drift."""
    document = json.loads(path.read_text())
    rows = [
        row
        for row in document.get("scans", [])
        if row.get("inclusion", {}).get("raw_capture_eligible") is True
    ]
    session_ids = [row.get("session_id") for row in rows]
    if len(rows) != EXPECTED_SESSIONS or len(set(session_ids)) != EXPECTED_SESSIONS:
        raise ValueError("DS2 quality report requires exactly the frozen 20 raw-eligible sessions")
    if any(
        not isinstance(session_id, str) or not session_id.startswith("scan-fw-")
        for session_id in session_ids
    ):
        raise ValueError("DS2 manifest contains an invalid session id")
    return rows


def _fetch_one(session_id: str) -> tuple[str, dict[str, Any]]:
    with urlopen(f"{TRACKING_API}/{session_id}", timeout=30) as response:  # noqa: S310
        envelope = json.load(response)
    if envelope.get("state") != "complete" or not isinstance(envelope.get("product"), dict):
        raise ValueError(f"{session_id}: V14 tracking product is not complete")
    return session_id, envelope["product"]


def fetch_products(session_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch completed products concurrently; source rows remain immutable."""
    with ThreadPoolExecutor(max_workers=min(8, len(session_ids))) as pool:
        fetched = list(pool.map(_fetch_one, session_ids))
    products = dict(fetched)
    if set(products) != set(session_ids):
        raise ValueError("tracking endpoint did not return the exact frozen DS2 session set")
    return products


def sanitized_product(product: dict[str, Any]) -> dict[str, Any]:
    """Keep only quality evidence; omit site and any position-diagnostic fields."""
    top_fields = (
        "schema_version",
        "analysis_id",
        "session_id",
        "capture_mode",
        "sample_rate_hz",
        "input_manifest_sha256",
        "analysis_manifest_sha256",
        "configuration_digest",
        "trajectory_state",
        "tle_state",
        "reasons",
        "projected_candidate_count",
        "physical_group_count",
        "eligible_group_count",
        "attempted_group_count",
        "deferred_group_count",
        "group_limit",
        "candidate_only",
        "identity_claimed",
        "tle_residual_partition_policy",
        "control_comparison_policy",
    )
    return {
        **{key: product.get(key) for key in top_fields},
        "tracklets": product.get("tracklets", []),
        "tle_candidates": product.get("tle_candidates", []),
        "track_reviews": product.get("track_reviews", []),
    }


def control_outcome(candidate: dict[str, Any]) -> dict[str, Any]:
    """Describe diagnostic controls without turning them into an identity claim."""
    nominal = candidate.get("nominal_heldout_negative_log_score")
    radio = candidate.get("radio_null_heldout_negative_log_score")
    minus = candidate.get("wrong_time_minus_500_heldout_negative_log_score")
    plus = candidate.get("wrong_time_plus_500_heldout_negative_log_score")
    values = (nominal, radio, minus, plus)
    if not all(isinstance(value, (int, float)) for value in values):
        return {
            "radio_null_delta": None,
            "wrong_time_minus_delta": None,
            "wrong_time_plus_delta": None,
            "nominal_beats_radio_null": None,
            "nominal_beats_both_wrong_times": None,
        }
    # Lower negative log score is preferable.  Positive deltas favor nominal.
    return {
        "radio_null_delta": radio - nominal,
        "wrong_time_minus_delta": minus - nominal,
        "wrong_time_plus_delta": plus - nominal,
        "nominal_beats_radio_null": nominal < radio,
        "nominal_beats_both_wrong_times": nominal < minus and nominal < plus,
    }


def build_rows(
    manifest_rows: list[dict[str, Any]], products: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract session, tracklet, review, and candidate tables from V14 products."""
    sessions: list[dict[str, Any]] = []
    tracklets: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for manifest in manifest_rows:
        session_id = manifest["session_id"]
        product = products[session_id]
        if product.get("input_manifest_sha256") != manifest.get("input_manifest_sha256"):
            raise ValueError(f"{session_id}: tracking product binding differs from frozen manifest")
        product_tracklets = product.get("tracklets", [])
        product_reviews = product.get("track_reviews", [])
        product_candidates = product.get("tle_candidates", [])
        sessions.append(
            {
                "session_id": session_id,
                "radio_id": manifest.get("radio_id"),
                "sample_rate_hz": manifest.get("sample_rate_hz"),
                "selected_edge": manifest.get("selected_edge"),
                "retained_visits": manifest.get("retained_visits"),
                "source_span_seconds": manifest.get("source_span_seconds"),
                "tracklet_count": len(product_tracklets),
                "review_count": len(product_reviews),
                "candidate_group_count": len(product_candidates),
                "tracklet_observation_count": sum(
                    int(tracklet.get("observation_count", 0)) for tracklet in product_tracklets
                ),
                "review_observation_count": sum(
                    int(review.get("observation_count", 0)) for review in product_reviews
                ),
                "eligible_group_count": product.get("eligible_group_count"),
                "attempted_group_count": product.get("attempted_group_count"),
                "deferred_group_count": product.get("deferred_group_count"),
                "projected_candidate_count": product.get("projected_candidate_count"),
                "analysis_manifest_sha256": product.get("analysis_manifest_sha256"),
                "configuration_digest": product.get("configuration_digest"),
            }
        )
        for tracklet in product_tracklets:
            start = tracklet.get("start_utc_ns")
            end = tracklet.get("end_utc_ns")
            span = (end - start) / 1e9 if isinstance(start, int) and isinstance(end, int) else None
            tracklets.append(
                {
                    "session_id": session_id,
                    "radio_id": manifest.get("radio_id"),
                    "sample_rate_hz": manifest.get("sample_rate_hz"),
                    "tracklet_id": tracklet.get("tracklet_id"),
                    "receiver_id": tracklet.get("receiver_id"),
                    "channel": tracklet.get("channel"),
                    "edge": tracklet.get("edge"),
                    "actual_rf_hz": tracklet.get("actual_rf_hz"),
                    "observation_count": tracklet.get("observation_count"),
                    "span_seconds": span,
                    "normalized_rate_hz_per_s": tracklet.get("normalized_rate_hz_per_s"),
                    "residual_rms_hz": tracklet.get("residual_rms_hz"),
                }
            )
        for review in product_reviews:
            reviewed = review.get("candidates", [])
            winner = next((row for row in reviewed if row.get("rank") == 1), None)
            reviews.append(
                {
                    "session_id": session_id,
                    "radio_id": manifest.get("radio_id"),
                    "tracklet_id": review.get("tracklet_id"),
                    "channel": review.get("channel"),
                    "edge": review.get("edge"),
                    "start_seconds": review.get("start_s"),
                    "end_seconds": review.get("end_s"),
                    "span_seconds": (
                        review["end_s"] - review["start_s"]
                        if isinstance(review.get("start_s"), (int, float))
                        and isinstance(review.get("end_s"), (int, float))
                        else None
                    ),
                    "observation_count": review.get("observation_count"),
                    "fit_observation_count": review.get("fit_observation_count"),
                    "randomized_evaluation_observation_count": review.get(
                        "randomized_evaluation_observation_count"
                    ),
                    "reviewed_candidate_count": len(reviewed),
                    "rank1_catalog_number": None
                    if winner is None
                    else winner.get("catalog_number"),
                    "rank1_fit_rms_hz": None if winner is None else winner.get("fit_rms_hz"),
                    "rank1_randomized_evaluation_rms_hz": (
                        None if winner is None else winner.get("randomized_evaluation_rms_hz")
                    ),
                }
            )
            for candidate in reviewed:
                candidates.append(
                    {
                        "row_kind": "review_candidate",
                        "session_id": session_id,
                        "radio_id": manifest.get("radio_id"),
                        "tracklet_id": review.get("tracklet_id"),
                        "rank": candidate.get("rank"),
                        "catalog_number": candidate.get("catalog_number"),
                        "fit_rms_hz": candidate.get("fit_rms_hz"),
                        "randomized_evaluation_rms_hz": candidate.get(
                            "randomized_evaluation_rms_hz"
                        ),
                    }
                )
        # Physical-group candidates carry abstention and control diagnostics.
        for candidate in product_candidates:
            diagnostics = control_outcome(candidate)
            candidates.append(
                {
                    "session_id": session_id,
                    "radio_id": manifest.get("radio_id"),
                    "tracklet_id": candidate.get("representative_tracklet_id"),
                    "rank": candidate.get("hypothesis_rank"),
                    "catalog_number": candidate.get("leading_catalog_number"),
                    "support_span_seconds": candidate.get("support_span_s"),
                    "source_observation_count": candidate.get("source_observation_count"),
                    "scored_observation_count": candidate.get("scored_observation_count"),
                    "training_runner_nll_margin": candidate.get(
                        "training_runner_negative_log_score_margin"
                    ),
                    "heldout_runner_nll_margin": candidate.get(
                        "heldout_runner_negative_log_score_margin"
                    ),
                    "heldout_rank": candidate.get("training_leader_heldout_rank"),
                    "leading_candidate_persisted_on_heldout": candidate.get(
                        "leading_candidate_persisted_on_heldout"
                    ),
                    "abstention_recommended": candidate.get("abstention_recommended"),
                    "abstention_reasons": "|".join(candidate.get("abstention_reasons", [])),
                    "selected_tau_seconds": candidate.get("selected_tau_s"),
                    **diagnostics,
                    "row_kind": "physical_group_candidate",
                }
            )
    return sessions, tracklets, reviews, candidates


def numeric(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]


def summarize(
    sessions: list[dict[str, Any]],
    tracklets: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    manifest_path: Path,
    source_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Build the report summary, including explicitly scoped DS1 context."""
    physical = [row for row in candidates if row.get("row_kind") == "physical_group_candidate"]
    rank1 = [
        row
        for row in candidates
        if row.get("row_kind") != "physical_group_candidate" and row.get("rank") == 1
    ]
    by_radio: dict[str, dict[str, Any]] = {}
    for radio_id in sorted({str(row["radio_id"]) for row in sessions}):
        radio_sessions = [row for row in sessions if str(row["radio_id"]) == radio_id]
        radio_tracklets = [row for row in tracklets if str(row["radio_id"]) == radio_id]
        radio_reviews = [row for row in reviews if str(row["radio_id"]) == radio_id]
        by_radio[radio_id] = {
            "sessions": len(radio_sessions),
            "sample_rates_hz": sorted({row["sample_rate_hz"] for row in radio_sessions}),
            "tracklets": len(radio_tracklets),
            "tracklet_observations": sum(
                int(row["observation_count"] or 0) for row in radio_tracklets
            ),
            "reviewed_tracklets": len(radio_reviews),
            "tracklet_span_seconds": distribution(numeric(radio_tracklets, "span_seconds")),
            "tracklet_residual_rms_hz": distribution(numeric(radio_tracklets, "residual_rms_hz")),
            "rank1_randomized_evaluation_rms_hz": distribution(
                numeric(
                    [row for row in rank1 if str(row.get("radio_id")) == radio_id],
                    "randomized_evaluation_rms_hz",
                )
            ),
        }
    abstentions = Counter(
        reason
        for row in physical
        for reason in str(row.get("abstention_reasons") or "").split("|")
        if reason
    )
    controls = {
        "physical_group_candidates": len(physical),
        "candidate_persisted_on_randomized_holdout": sum(
            row.get("leading_candidate_persisted_on_heldout") is True for row in physical
        ),
        "abstention_recommended": sum(
            row.get("abstention_recommended") is True for row in physical
        ),
        "abstention_reason_counts": dict(sorted(abstentions.items())),
        "nominal_beats_radio_null_diagnostic": sum(
            row.get("nominal_beats_radio_null") is True for row in physical
        ),
        "nominal_beats_both_wrong_time_controls_diagnostic": sum(
            row.get("nominal_beats_both_wrong_times") is True for row in physical
        ),
        "radio_null_score_delta": distribution(numeric(physical, "radio_null_delta")),
        "wrong_time_minus_score_delta": distribution(numeric(physical, "wrong_time_minus_delta")),
        "wrong_time_plus_score_delta": distribution(numeric(physical, "wrong_time_plus_delta")),
        "note": (
            "Positive score delta favors nominal because lower negative-log score is better. "
            "These controls are diagnostic only and do not establish identity."
        ),
    }
    return {
        "schema": "ds2-corpus-quality/v1",
        "created_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "scope": {
            "dataset": "DS2",
            "frozen_raw_eligible_sessions": EXPECTED_SESSIONS,
            "analysis": "descriptive V14 tracking-product quality only",
            "positioning_or_reference_inputs": "not read or used",
            "holdout_policy": (
                "existing V14 deterministic randomized observation split; no chronological holdout"
            ),
        },
        "bindings": {
            "frozen_inventory_path": str(manifest_path.relative_to(HERE.parents[1])),
            "frozen_inventory_sha256": file_digest(manifest_path),
            "canonical_sanitized_tracking_snapshot_sha256": canonical_digest(source_snapshot),
            "tracking_analysis_ids": sorted(
                {str(row.get("analysis_id")) for row in source_snapshot.values()}
            ),
            "tracking_configuration_digests": sorted(
                {str(row.get("configuration_digest")) for row in source_snapshot.values()}
            ),
        },
        "corpus": {
            "sessions": len(sessions),
            "source_span_seconds": distribution(numeric(sessions, "source_span_seconds")),
            "retained_visits": distribution(numeric(sessions, "retained_visits")),
            "tracklets": len(tracklets),
            "tracklet_observations": sum(int(row["observation_count"] or 0) for row in tracklets),
            "reviews": len(reviews),
            "review_observations": sum(int(row["observation_count"] or 0) for row in reviews),
            "physical_group_candidates": len(physical),
            "radio_cohorts": by_radio,
        },
        "quality": {
            "tracklet_observation_count": distribution(numeric(tracklets, "observation_count")),
            "tracklet_span_seconds": distribution(numeric(tracklets, "span_seconds")),
            "tracklet_residual_rms_hz": distribution(numeric(tracklets, "residual_rms_hz")),
            "review_observation_count": distribution(numeric(reviews, "observation_count")),
            "review_span_seconds": distribution(numeric(reviews, "span_seconds")),
            "rank1_fit_rms_hz": distribution(numeric(reviews, "rank1_fit_rms_hz")),
            "rank1_randomized_evaluation_rms_hz": distribution(
                numeric(reviews, "rank1_randomized_evaluation_rms_hz")
            ),
            "rank1_reviewed_candidate_count": distribution(
                numeric(reviews, "reviewed_candidate_count")
            ),
            "rank1_randomized_evaluation_rms_threshold_counts": {
                "at_or_below_100_hz": sum(
                    isinstance(row.get("rank1_randomized_evaluation_rms_hz"), (int, float))
                    and row["rank1_randomized_evaluation_rms_hz"] <= 100.0
                    for row in reviews
                ),
                "at_or_below_200_hz": sum(
                    isinstance(row.get("rank1_randomized_evaluation_rms_hz"), (int, float))
                    and row["rank1_randomized_evaluation_rms_hz"] <= 200.0
                    for row in reviews
                ),
                "at_or_below_800_hz": sum(
                    isinstance(row.get("rank1_randomized_evaluation_rms_hz"), (int, float))
                    and row["rank1_randomized_evaluation_rms_hz"] <= 800.0
                    for row in reviews
                ),
            },
        },
        "controls": controls,
        "ds1_context": {
            "available_summary": {
                "source": "reports/2026_09_24_ds1/REPORT.md",
                "full_block_baseline_median_capped_held_rms_hz": 312.47,
                "full_block_shared_time_median_capped_held_rms_hz": 301.06,
                "scope": "eight completed multi-scan position-fit/start pairs",
            },
            "comparison_limit": (
                "DS2 numbers are native per-track review RMS under site-assisted catalogue "
                "reviews. DS1 numbers are selected multi-scan geographic-fit 800-Hz-capped "
                "aggregate RMS. They are not directly comparable as a cleanliness ratio; the "
                "DS1 values are retained only as available historical context."
            ),
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _ecdf(values: list[float]) -> tuple[list[float], list[float]]:
    ordered = sorted(values)
    return ordered, [(index + 1) / len(ordered) for index in range(len(ordered))]


def plot(
    sessions: list[dict[str, Any]],
    tracklets: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    physical: list[dict[str, Any]],
    path: Path,
) -> None:
    """Render descriptive quality panels only; no location axes or reference inputs."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    colors = {
        radio: color
        for radio, color in zip(
            sorted({str(r["radio_id"]) for r in sessions}),
            ("#1f77b4", "#ff7f0e", "#2ca02c"),
            strict=False,
        )
    }
    for radio, color in colors.items():
        rows = [row for row in sessions if str(row["radio_id"]) == radio]
        axes[0, 0].scatter(
            [row["tracklet_count"] for row in rows],
            [row["tracklet_observation_count"] for row in rows],
            label=radio,
            color=color,
            s=48,
        )
    axes[0, 0].set_title("Per-session tracking yield")
    axes[0, 0].set_xlabel("Tracklets")
    axes[0, 0].set_ylabel("Tracklet observations")
    axes[0, 0].legend(title="Radio")
    axes[0, 0].grid(alpha=0.25)

    tracklet_rms = numeric(tracklets, "residual_rms_hz")
    held_rms = numeric(reviews, "rank1_randomized_evaluation_rms_hz")
    axes[0, 1].boxplot(
        [tracklet_rms, held_rms],
        tick_labels=["Tracklet\nresidual", "Rank-1 randomized\nevaluation"],
        showfliers=False,
    )
    axes[0, 1].set_title("Native residual distributions")
    axes[0, 1].set_ylabel("RMS (Hz)")
    axes[0, 1].grid(axis="y", alpha=0.25)

    for label, values, color in (
        ("tracklet residual", tracklet_rms, "#1f77b4"),
        ("rank-1 randomized evaluation", held_rms, "#d62728"),
    ):
        x, y = _ecdf(values)
        axes[1, 0].step(x, y, where="post", label=label, color=color)
    axes[1, 0].set_title("Residual RMS empirical CDF")
    axes[1, 0].set_xlabel("RMS (Hz)")
    axes[1, 0].set_ylabel("Fraction at or below RMS")
    axes[1, 0].set_xlim(left=0)
    axes[1, 0].grid(alpha=0.25)
    axes[1, 0].legend()

    outcomes = {
        "Persisted\non holdout": sum(
            row.get("leading_candidate_persisted_on_heldout") is True for row in physical
        ),
        "No\nabstention": sum(row.get("abstention_recommended") is False for row in physical),
        "Beats\nradio-null": sum(row.get("nominal_beats_radio_null") is True for row in physical),
        "Beats both\nwrong-time": sum(
            row.get("nominal_beats_both_wrong_times") is True for row in physical
        ),
    }
    axes[1, 1].bar(list(outcomes), list(outcomes.values()), color="#4c78a8")
    axes[1, 1].set_title("Physical-group diagnostic outcomes")
    axes[1, 1].set_ylabel("Candidates")
    axes[1, 1].grid(axis="y", alpha=0.25)
    axes[1, 1].text(
        0.98,
        0.98,
        "Diagnostic controls only;\nnot identity claims",
        ha="right",
        va="top",
        transform=axes[1, 1].transAxes,
        fontsize=9,
    )
    fig.suptitle("DS2: sealed 20-session tracking-product quality", fontsize=16)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--products",
        type=Path,
        help="read a sanitized product snapshot instead of the local tracking endpoint",
    )
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    manifest_rows = strict_manifest(args.manifest)
    session_ids = [row["session_id"] for row in manifest_rows]
    if args.products:
        products = json.loads(args.products.read_text())
    else:
        products = fetch_products(session_ids)
    if set(products) != set(session_ids):
        raise ValueError("quality source does not bind exactly the frozen DS2 session IDs")
    snapshot = {session_id: sanitized_product(products[session_id]) for session_id in session_ids}
    sessions, tracklets, reviews, candidates = build_rows(manifest_rows, snapshot)
    summary = summarize(
        sessions,
        tracklets,
        reviews,
        candidates,
        manifest_path=args.manifest,
        source_snapshot=snapshot,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "tracking-products-sanitized.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    )
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_csv(args.output / "session-quality.csv", sessions)
    write_csv(args.output / "tracklet-quality.csv", tracklets)
    write_csv(args.output / "review-quality.csv", reviews)
    write_csv(args.output / "candidate-quality.csv", candidates)
    plot(
        sessions,
        tracklets,
        reviews,
        [row for row in candidates if row.get("row_kind") == "physical_group_candidate"],
        args.output / "quality-overview.png",
    )
    print(
        json.dumps(
            {"sessions": len(sessions), "tracklets": len(tracklets), "reviews": len(reviews)}
        )
    )


if __name__ == "__main__":
    main()
