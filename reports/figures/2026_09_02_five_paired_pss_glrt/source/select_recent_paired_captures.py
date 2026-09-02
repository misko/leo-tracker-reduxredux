#!/usr/bin/env python3
"""Freeze a read-only, evidence-based five-capture PSS/GLRT cohort.

The selector deliberately uses only the promoted Standard analysis and the
2.5 MS/s full-capture GLRT product.  Native-25 PSS outcomes are not inspected,
so the scientific cohort cannot be selected on the desired comparison result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default="postgresql:///leo_tracker")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--window-end-utc",
        default="2026-09-02T02:36:07.288954Z",
        help="fixed cohort cutoff; the study window begins eight hours earlier",
    )
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument(
        "--minimum-native25-density",
        type=float,
        default=0.50,
        help="minimum observed/logical sample density required for native-25 comparison",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("window end must carry an explicit UTC offset")
    return parsed.astimezone(UTC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _bulk_path(uri: str, root: Path) -> Path:
    prefix = "bulk://"
    if not uri.startswith(prefix):
        raise ValueError(f"non-bulk product URI: {uri}")
    return root / uri.removeprefix(prefix)


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _glrt_metrics(document: dict[str, Any]) -> dict[str, Any]:
    passing = [
        window
        for segment in document["segments"]
        for window in segment["windows"]
        if window["passed_margin_gate"]
    ]
    tracks = [track for segment in document["segments"] for track in segment["hough"]["tracks"]]
    accounting = document["accounting"]
    valid = int(accounting["valid_count"])
    return {
        "valid_window_count": valid,
        "passing_window_count": int(accounting["passing_count"]),
        "passing_fraction": float(accounting["passing_count"] / valid),
        "median_passing_margin": _median([float(window["glrt_margin"]) for window in passing]),
        "median_passing_exact_score": _median(
            [float(window["glrt_exact_score"]) for window in passing]
        ),
        "median_passing_control_score": _median(
            [float(window["glrt_control_score"]) for window in passing]
        ),
        "median_robust_line_rms_hz": _median(
            [float(window["robust_residual_rms_hz"]) for window in passing]
        ),
        "hough_track_count": len(tracks),
        "hough_observation_count": sum(int(track["observation_count"]) for track in tracks),
        "longest_hough_observation_count": max(
            (int(track["observation_count"]) for track in tracks), default=0
        ),
        "longest_hough_span_s": max(
            (
                float(track["global_end_time_s"]) - float(track["global_start_time_s"])
                for track in tracks
            ),
            default=0.0,
        ),
    }


def _stream_summary(row: dict[str, Any]) -> dict[str, Any]:
    attributes = row["attributes"]
    settings = attributes["applied_settings"]
    continuity = attributes["continuity"]
    timing = attributes["timing"]
    return {
        "stream_id": row["stream_id"],
        "manifest_ordinal": int(row["manifest_ordinal"]),
        "radio_id": row["radio_id"],
        "sample_rate_hz": int(row["sample_rate_hz"]),
        "receiver_ids": list(row["receiver_ids"]),
        "center_frequency_hz": int(settings["center_frequency_hz"]),
        "rf_bandwidth_hz": int(settings["bandwidth_hz"]),
        "logical_sample_count": int(attributes["logical_sample_count"]),
        "observed_sample_count": int(attributes["observed_sample_count"]),
        "missing_sample_count": int(attributes["zero_fill_sample_count"]),
        "observed_density": float(
            int(attributes["observed_sample_count"]) / int(attributes["logical_sample_count"])
        ),
        "continuity_gap_count": int(continuity["gap_count"]),
        "continuity_segment_count": int(continuity["segment_count"]),
        "first_sample_timing": timing["first_sample"],
        "last_sample_timing": timing["last_sample"],
        "validity_inventory_sha256": attributes["validity_inventory_sha256"],
        "timeline_sha256": attributes["timeline_sha256"],
        "gap_map_sha256": attributes["gap_map_sha256"],
    }


def main() -> None:
    arguments = _arguments()
    if arguments.count < 1:
        raise ValueError("selection count must be positive")
    if not 0.0 < arguments.minimum_native25_density <= 1.0:
        raise ValueError("minimum native-25 density must lie in (0, 1]")
    window_end = _parse_utc(arguments.window_end_utc)
    window_start = window_end - timedelta(hours=8)
    with psycopg.connect(arguments.database_url, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        stream_rows = connection.execute(
            """
            SELECT cs.id AS session_id, cs.observed_start_at, cs.bundle_uri,
                   cs.manifest_digest, cs.raw_available, rs.id AS stream_id,
                   rs.manifest_ordinal, rs.radio_id, rs.sample_rate_hz,
                   rs.receiver_ids, rs.attributes
            FROM capture_session cs
            JOIN radio_stream rs ON rs.session_id = cs.id
            JOIN current_pipeline_analysis cpa
              ON cpa.session_id = cs.id AND cpa.pipeline_lane = 'standard'
            JOIN analysis_run ar ON ar.id = cpa.run_id AND ar.state = 'succeeded'
            WHERE cs.observed_start_at >= %s AND cs.observed_start_at < %s
              AND cs.raw_available
            ORDER BY cs.observed_start_at, rs.manifest_ordinal
            """,
            (window_start, window_end),
        ).fetchall()
        product_rows = connection.execute(
            """
            SELECT ar.session_id, ap.scope_key, ap.logical_uri, ap.digest,
                   ap.schema_version, rsb.document AS binding
            FROM current_pipeline_analysis cpa
            JOIN analysis_run ar ON ar.id = cpa.run_id AND ar.state = 'succeeded'
            JOIN capture_session cs ON cs.id = ar.session_id
            JOIN analysis_product ap ON ap.run_id = ar.id
            JOIN run_subject_binding rsb
              ON rsb.run_id = ar.id AND rsb.scope_id = ap.scope_id
            WHERE cs.observed_start_at >= %s AND cs.observed_start_at < %s
              AND cpa.pipeline_lane = 'standard'
              AND ap.kind = 'standard.full-capture-glrt20ms'
              AND ap.schema_version = 2 AND ap.available
            ORDER BY ar.session_id, (rsb.document->>'receiver_id')::int
            """,
            (window_start, window_end),
        ).fetchall()

    streams_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stream_rows:
        streams_by_session[str(row["session_id"])].append(row)
    products_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in product_rows:
        products_by_session[str(row["session_id"])].append(row)

    eligible: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for session_id, rows in streams_by_session.items():
        rates = sorted(int(row["sample_rate_hz"]) for row in rows)
        if rates != [2_500_000, 25_000_000]:
            exclusions.append({"session_id": session_id, "reason": "not exact paired 2.5/25"})
            continue
        low = next(row for row in rows if int(row["sample_rate_hz"]) == 2_500_000)
        high = next(row for row in rows if int(row["sample_rate_hz"]) == 25_000_000)
        high_attributes = high["attributes"]
        high_density = float(
            int(high_attributes["observed_sample_count"])
            / int(high_attributes["logical_sample_count"])
        )
        if high_density < arguments.minimum_native25_density:
            exclusions.append(
                {
                    "session_id": session_id,
                    "reason": (
                        f"native-25 observed density {high_density:.6f} below "
                        f"{arguments.minimum_native25_density:.6f}"
                    ),
                }
            )
            continue
        products = [
            row
            for row in products_by_session[session_id]
            if int(row["binding"]["sample_rate_hz"]) == 2_500_000
        ]
        if len(products) != 2 or sorted(int(row["binding"]["receiver_id"]) for row in products) != [
            0,
            1,
        ]:
            exclusions.append(
                {"session_id": session_id, "reason": "missing dual-receiver 2.5M GLRT V2"}
            )
            continue
        glrt: list[dict[str, Any]] = []
        for product in products:
            path = _bulk_path(str(product["logical_uri"]), arguments.bulk_root)
            observed_digest = _sha256(path)
            if observed_digest != product["digest"]:
                raise ValueError(f"GLRT product digest mismatch for {session_id}: {path}")
            document = json.loads(path.read_text(encoding="utf-8"))
            binding = product["binding"]
            glrt.append(
                {
                    "receiver_id": int(binding["receiver_id"]),
                    "physical_receiver_id": binding["physical_receiver_id"],
                    "starlink_channel": int(binding["starlink_channel"]),
                    "starlink_edge": binding["starlink_edge"],
                    "scope_key": product["scope_key"],
                    "logical_uri": product["logical_uri"],
                    "path": str(path),
                    "digest": observed_digest,
                    **_glrt_metrics(document),
                }
            )
        glrt.sort(key=lambda item: int(item["receiver_id"]))
        manifest_path = _bulk_path(str(low["bundle_uri"]), arguments.bulk_root) / "manifest.json"
        manifest_digest = _sha256(manifest_path)
        if manifest_digest != low["manifest_digest"]:
            raise ValueError(f"manifest digest mismatch for {session_id}")
        best = max(glrt, key=lambda item: float(item["passing_fraction"]))
        eligible.append(
            {
                "session_id": session_id,
                "observed_start_utc": low["observed_start_at"].astimezone(UTC).isoformat(),
                "bundle_uri": low["bundle_uri"],
                "manifest_path": str(manifest_path),
                "manifest_digest": manifest_digest,
                "stream_2p5m": _stream_summary(low),
                "stream_25m": _stream_summary(high),
                "glrt_2p5m": glrt,
                "rank_fields": {
                    "best_receiver_id": int(best["receiver_id"]),
                    "best_passing_fraction": float(best["passing_fraction"]),
                    "best_median_passing_margin": float(best["median_passing_margin"]),
                    "best_longest_hough_span_s": max(
                        float(item["longest_hough_span_s"]) for item in glrt
                    ),
                    "total_passing_window_count": sum(
                        int(item["passing_window_count"]) for item in glrt
                    ),
                },
            }
        )

    eligible.sort(
        key=lambda item: (
            -float(item["rank_fields"]["best_passing_fraction"]),
            -float(item["rank_fields"]["best_median_passing_margin"]),
            -float(item["rank_fields"]["best_longest_hough_span_s"]),
            str(item["session_id"]),
        )
    )
    if len(eligible) < arguments.count:
        raise ValueError(f"only {len(eligible)} eligible paired captures are available")
    selected = eligible[: arguments.count]
    document = {
        "schema_version": 1,
        "analysis_kind": "read-only-promoted-glrt-paired-capture-selection",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "window": {
            "start_utc": window_start.isoformat(),
            "end_utc": window_end.isoformat(),
            "duration_hours": 8,
            "end_semantics": "inclusive start, exclusive end",
        },
        "selection_policy": {
            "required_rates_hz": [2_500_000, 25_000_000],
            "required_promoted_pipeline_lane": "standard",
            "required_analysis_state": "succeeded",
            "required_glrt_product": "standard.full-capture-glrt20ms.v2",
            "required_2p5_receiver_ids": [0, 1],
            "minimum_native25_observed_density": arguments.minimum_native25_density,
            "rank_order": [
                "descending best receiver passing fraction",
                "descending best receiver median passing margin",
                "descending longest Hough span",
                "ascending session ID",
            ],
            "native_25_pss_outcomes_used_for_selection": False,
            "selection_count": arguments.count,
        },
        "accounting": {
            "current_succeeded_session_count": len(streams_by_session),
            "eligible_paired_session_count": len(eligible),
            "selected_session_count": len(selected),
            "excluded_session_count": len(exclusions),
        },
        "selected": selected,
        "eligible_ranked": eligible,
        "exclusions": exclusions,
    }
    payload = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(payload, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "sha256": _sha256(arguments.output),
                "selected": [item["session_id"] for item in selected],
                "eligible_count": len(eligible),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
