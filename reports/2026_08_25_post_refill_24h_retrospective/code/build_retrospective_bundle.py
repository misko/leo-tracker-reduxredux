#!/usr/bin/env python3
"""Rebuild the fixed 24-hour post-refill retrospective inventory.

This is report-owned code, deliberately kept outside the application package.
It reads the sealed PostgreSQL catalogue and read-only bulk manifests, validates
their digests, performs the documented lightweight linear-CFO overlap screen,
and writes the machine-readable and Markdown inventories beside this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

WINDOW_START = "2026-08-24T20:28:52.780539832Z"
WINDOW_END = "2026-08-25T20:28:52.780539832Z"
REFERENCE_RF_HZ = 11_000_000_000.0
MINIMUM_COMMON_OVERLAP_S = 2.0
MAXIMUM_NORMALIZED_SLOPE_SPREAD_HZ_S = 100.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _bulk_path(uri: str, bulk_root: Path) -> Path:
    prefix = "bulk://"
    if not uri.startswith(prefix):
        raise ValueError(f"not a bulk URI: {uri}")
    path = bulk_root / uri[len(prefix) :]
    if uri.startswith("bulk://recordings/") and path.name != "manifest.json":
        path /= "manifest.json"
    return path


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    payload = value.get("payload", value)
    if not isinstance(payload, dict):
        raise ValueError(f"expected payload object: {path}")
    return payload


def _query_rows(database: str) -> list[dict[str, str]]:
    sql = f"""
COPY (
  SELECT
    cs.id AS capture_session_id,
    to_char(cs.observed_start_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS observed_start_utc,
    to_char(cs.observed_end_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS observed_end_utc,
    cs.profile_revision_id,
    cs.state AS capture_state,
    cs.bundle_uri AS recording_manifest_uri,
    cs.manifest_digest AS recording_manifest_digest,
    cs.raw_available,
    ar.id AS analysis_run_id,
    ar.pipeline_lane,
    ar.pipeline_release_id,
    ar.trigger,
    ar.state AS analysis_state,
    to_char(ar.created_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS analysis_created_utc,
    to_char(ar.sealed_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS analysis_sealed_utc,
    ar.manifest_uri AS analysis_manifest_uri,
    ar.manifest_digest AS analysis_manifest_digest,
    ar.input_manifest_digest,
    ar.raw_integrity_attestation_id,
    count(ap.id) AS product_count,
    count(*) FILTER (WHERE ap.status = 'complete') AS complete_products,
    count(*) FILTER (WHERE ap.status = 'no_result') AS no_result_products,
    count(*) FILTER (WHERE ap.status = 'partial_coverage') AS partial_products,
    coalesce(sum(ap.byte_size), 0) AS product_bytes
  FROM public.capture_session AS cs
  JOIN public.analysis_run AS ar ON ar.session_id = cs.id
  LEFT JOIN public.analysis_product AS ap ON ap.run_id = ar.id
  WHERE cs.observed_start_at >= '{WINDOW_START}'::timestamptz
    AND cs.observed_start_at <= '{WINDOW_END}'::timestamptz
    AND cs.state = 'committed'
  GROUP BY cs.id, ar.id
  ORDER BY cs.observed_start_at, ar.created_at
) TO STDOUT WITH CSV HEADER
"""
    command = [
        "sudo",
        "-n",
        "-u",
        "postgres",
        "psql",
        "-X",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return list(csv.DictReader(io.StringIO(completed.stdout)))


def _products_by_scope(run_manifest: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for product in run_manifest.get("products", []):
        if not isinstance(product, dict):
            continue
        kind = product.get("kind")
        scope = product.get("scope_key")
        if isinstance(kind, str) and isinstance(scope, str):
            result.setdefault(scope, {})[kind] = product
    return result


def _screen_capture(
    recording: dict[str, Any],
    run_manifest: dict[str, Any],
    bulk_root: Path,
) -> dict[str, Any]:
    profile = recording["capture_plan"]["profile_revision"]["profile"]
    lnb_lo_hz = int(profile["lnb_lo_hz"])
    rf_by_stream: dict[str, int] = {}
    for stream in recording["streams"]:
        rf_by_stream[str(stream["stream_id"])] = lnb_lo_hz + int(
            stream["applied_settings"]["center_frequency_hz"]
        )

    path_rows: list[dict[str, Any]] = []
    path_statuses: Counter[str] = Counter()
    for _scope, products in sorted(_products_by_scope(run_manifest).items()):
        report_product = products.get("standard.path-report") or products.get(
            "research.path-report"
        )
        if report_product is None:
            continue
        report = _load(_bulk_path(str(report_product["logical_uri"]), bulk_root))
        raw_report = report.get("raw_report", {})
        if not isinstance(raw_report, dict):
            continue
        status = str(report.get("status", "unknown"))
        path_statuses[status] += 1
        stream_id = str(raw_report["stream_id"])
        radio_id = str(raw_report["radio_id"])
        receiver_id = int(raw_report["receiver_id"])
        path_id = f"{stream_id}/{radio_id}/RX{receiver_id}"
        timing = raw_report.get("timing", {})
        first_utc_ns = timing.get("first_estimate_utc_ns")
        bank_product = products.get("standard.dealiased-trajectory-bank") or products.get(
            "research.dealiased-trajectory-bank"
        )
        if (
            status not in {"complete", "partial", "partial_coverage"}
            or bank_product is None
            or first_utc_ns is None
        ):
            path_rows.append({"path_id": path_id, "status": status, "branches": []})
            continue
        bank = _load(_bulk_path(str(bank_product["logical_uri"]), bulk_root))
        pilot_by_branch: dict[str, tuple[int, int]] = {}
        pilot_product = products.get("standard.pilot-doppler-segments") or products.get(
            "research.pilot-doppler-segments"
        )
        if pilot_product is not None:
            pilot = _load(_bulk_path(str(pilot_product["logical_uri"]), bulk_root))
            for summary in pilot.get("trajectory_summaries", []):
                if not isinstance(summary, dict):
                    continue
                branch_id = summary.get("source_branch_id")
                if isinstance(branch_id, str):
                    qualified, analyzed = pilot_by_branch.get(branch_id, (0, 0))
                    pilot_by_branch[branch_id] = (
                        max(qualified, int(summary.get("qualified_segment_count", 0))),
                        max(analyzed, int(summary.get("analyzed_segment_count", 0))),
                    )
        branches: list[dict[str, Any]] = []
        for branch in bank.get("branches", []):
            if not isinstance(branch, dict):
                continue
            model = branch.get("model", {})
            coefficients = model.get("coefficients_hz", []) if isinstance(model, dict) else []
            if not isinstance(coefficients, list) or len(coefficients) != 2:
                continue
            branch_id = str(branch["branch_id"])
            qualified, analyzed = pilot_by_branch.get(branch_id, (0, 0))
            rf_hz = rf_by_stream[stream_id]
            branches.append(
                {
                    "branch_id": branch_id,
                    "start_utc_ns": int(first_utc_ns)
                    + round(float(branch["start_s"]) * 1_000_000_000),
                    "end_utc_ns": int(first_utc_ns) + round(float(branch["end_s"]) * 1_000_000_000),
                    "normalized_slope_hz_s": float(coefficients[0]) * REFERENCE_RF_HZ / rf_hz,
                    "observation_count": len(branch.get("observation_ids", [])),
                    "qualified_pilot_segment_count": qualified,
                    "analyzed_pilot_segment_count": analyzed,
                    "rf_hz": rf_hz,
                }
            )
        path_rows.append({"path_id": path_id, "status": status, "branches": branches})

    best: dict[str, Any] | None = None
    branch_paths = [path for path in path_rows if path["branches"]]
    for path_count in range(min(4, len(branch_paths)), 1, -1):
        candidates: list[dict[str, Any]] = []
        for paths in itertools.combinations(branch_paths, path_count):
            for branches in itertools.product(*(path["branches"] for path in paths)):
                start_ns = max(branch["start_utc_ns"] for branch in branches)
                end_ns = min(branch["end_utc_ns"] for branch in branches)
                overlap_s = (end_ns - start_ns) / 1_000_000_000
                slopes = [branch["normalized_slope_hz_s"] for branch in branches]
                spread = max(slopes) - min(slopes)
                if (
                    overlap_s < MINIMUM_COMMON_OVERLAP_S
                    or spread > MAXIMUM_NORMALIZED_SLOPE_SPREAD_HZ_S
                ):
                    continue
                candidates.append(
                    {
                        "path_count": path_count,
                        "band_relationship": (
                            "cross-band"
                            if len({branch["rf_hz"] for branch in branches}) > 1
                            else "same-band"
                        ),
                        "common_overlap_s": overlap_s,
                        "normalized_slope_spread_hz_s": spread,
                        "observation_count": sum(
                            branch["observation_count"] for branch in branches
                        ),
                        "qualified_pilot_segment_count": sum(
                            branch["qualified_pilot_segment_count"] for branch in branches
                        ),
                        "analyzed_pilot_segment_count": sum(
                            branch["analyzed_pilot_segment_count"] for branch in branches
                        ),
                        "path_ids": [path["path_id"] for path in paths],
                        "branch_ids": [branch["branch_id"] for branch in branches],
                    }
                )
        if candidates:
            best = max(
                candidates,
                key=lambda item: (
                    item["common_overlap_s"],
                    item["observation_count"],
                    item["qualified_pilot_segment_count"],
                    -item["normalized_slope_spread_hz_s"],
                ),
            )
            break

    if best is not None:
        band_label = "cross" if best["band_relationship"] == "cross-band" else "same"
        category = f"{best['path_count']}p-{band_label}"
    elif not branch_paths:
        category = "hard-null"
    elif len(branch_paths) == 1:
        category = "single-path"
    else:
        category = "fragmented"
    return {
        "category": category,
        "path_status_counts": dict(sorted(path_statuses.items())),
        "screen_selection": best,
    }


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = list(rows[0])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Capture and analysis identifiers",
        "",
        f"Fixed capture-start interval: `{WINDOW_START}` through `{WINDOW_END}` (inclusive).",
        "",
        "Every row is a committed capture with its single sealed analysis run. "
        "Full digests and product accounting are in "
        "`capture-analysis-inventory.csv` and `retrospective-data.json`.",
        "",
        "| UTC start | Capture session ID | Analysis run ID | Lane | Category |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            (
                "| {observed_start_utc} | `{capture_session_id}` | "
                "`{analysis_run_id}` | {pipeline_lane} | {screen_category} |"
            ).format(**row)
        )
    lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="leo_tracker")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--output-directory", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--hash-json-products", action="store_true")
    args = parser.parse_args()

    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    rows = _query_rows(args.database)
    if len(rows) != 89:
        raise RuntimeError(f"expected exactly 89 capture/run rows, found {len(rows)}")

    category_counts: Counter[str] = Counter()
    lane_counts: Counter[str] = Counter()
    product_status_counts: Counter[str] = Counter()
    stream_count = 0
    clean_stream_count = 0
    maximum_queue_high_water = 0
    maximum_refill_interval_ns = 0
    json_product_count = 0
    json_product_bytes = 0
    json_product_errors: list[str] = []
    enriched: list[dict[str, Any]] = []

    for raw_row in rows:
        row: dict[str, Any] = dict(raw_row)
        recording_path = _bulk_path(row["recording_manifest_uri"], args.bulk_root)
        analysis_path = _bulk_path(row["analysis_manifest_uri"], args.bulk_root)
        recording_digest = _sha256(recording_path)
        analysis_digest = _sha256(analysis_path)
        if recording_digest != row["recording_manifest_digest"]:
            raise RuntimeError(f"recording manifest digest mismatch: {recording_path}")
        if analysis_digest != row["analysis_manifest_digest"]:
            raise RuntimeError(f"analysis manifest digest mismatch: {analysis_path}")
        if row["input_manifest_digest"] != row["recording_manifest_digest"]:
            raise RuntimeError(f"analysis input mismatch: {row['analysis_run_id']}")

        recording = _load(recording_path)
        run_manifest = _load(analysis_path)
        screen = _screen_capture(recording, run_manifest, args.bulk_root)
        category_counts[screen["category"]] += 1
        lane_counts[str(row["pipeline_lane"])] += 1
        for key, field in (
            ("complete", "complete_products"),
            ("no_result", "no_result_products"),
            ("partial_coverage", "partial_products"),
        ):
            product_status_counts[key] += int(row[field])

        streams = recording.get("streams", [])
        stream_count += len(streams)
        for stream in streams:
            continuity = stream.get("continuity", {})
            clean = (
                stream.get("state") == "complete"
                and int(stream.get("requested_sample_count", -1)) == 150_000_000
                and int(stream.get("captured_sample_count", -2)) == 150_000_000
                and continuity.get("schema_version") == 2
                and continuity.get("sample_loss_observable") is True
                and int(continuity.get("device_span_sample_count", -1)) == 150_000_000
                and all(
                    int(continuity.get(key, -1)) == 0
                    for key in (
                        "gap_count",
                        "missing_sample_count",
                        "overflow_count",
                        "enqueue_failure_count",
                        "terminal_rejected_gap_count",
                        "terminal_rejected_missing_sample_count",
                        "terminal_rejected_overflow_count",
                    )
                )
            )
            clean_stream_count += int(clean)
            maximum_queue_high_water = max(
                maximum_queue_high_water,
                int(continuity.get("queue_high_water_refills", 0)),
            )
            maximum_refill_interval_ns = max(
                maximum_refill_interval_ns,
                int(continuity.get("maximum_refill_service_interval_ns", 0)),
            )

        products = run_manifest.get("products", [])
        if len(products) != int(row["product_count"]):
            raise RuntimeError(f"product count mismatch: {row['analysis_run_id']}")
        if args.hash_json_products:
            for product in products:
                if product.get("media_type") != "application/json":
                    continue
                json_product_count += 1
                product_path = _bulk_path(str(product["logical_uri"]), args.bulk_root)
                if not product_path.is_file():
                    json_product_errors.append(f"missing:{product_path}")
                    continue
                size = product_path.stat().st_size
                json_product_bytes += size
                if size != int(product["byte_size"]):
                    json_product_errors.append(f"size:{product_path}")
                if _sha256(product_path) != product["digest"]:
                    json_product_errors.append(f"digest:{product_path}")

        selection = screen["screen_selection"] or {}
        row.update(
            {
                "recording_manifest_path": str(recording_path),
                "analysis_manifest_path": str(analysis_path),
                "screen_category": screen["category"],
                "screen_path_count": selection.get("path_count"),
                "screen_band_relationship": selection.get("band_relationship"),
                "screen_common_overlap_s": selection.get("common_overlap_s"),
                "screen_normalized_slope_spread_hz_s": selection.get(
                    "normalized_slope_spread_hz_s"
                ),
                "screen_observation_count": selection.get("observation_count"),
                "screen_qualified_pilot_segments": selection.get("qualified_pilot_segment_count"),
                "screen_analyzed_pilot_segments": selection.get("analyzed_pilot_segment_count"),
                "screen_path_ids": ";".join(selection.get("path_ids", [])),
                "screen_branch_ids": ";".join(selection.get("branch_ids", [])),
            }
        )
        enriched.append(row)

    expected_categories = {
        "4p-cross": 23,
        "4p-same": 21,
        "3p-cross": 8,
        "3p-same": 8,
        "2p-cross": 3,
        "2p-same": 16,
        "single-path": 4,
        "fragmented": 3,
        "hard-null": 3,
    }
    if dict(sorted(category_counts.items())) != dict(sorted(expected_categories.items())):
        raise RuntimeError(
            f"screen category census changed: {dict(sorted(category_counts.items()))}"
        )
    if clean_stream_count != stream_count or stream_count != 178:
        raise RuntimeError(f"continuity audit failed: {clean_stream_count}/{stream_count}")
    if json_product_errors:
        raise RuntimeError(f"JSON product audit failures: {json_product_errors[:5]}")

    summary = {
        "schema": "org.leo.research.post-refill-24h-retrospective/v1",
        "fixed_capture_start_window": {
            "start_utc": WINDOW_START,
            "end_utc": WINDOW_END,
            "inclusive": True,
        },
        "screen_rule": {
            "reference_rf_hz": REFERENCE_RF_HZ,
            "minimum_common_overlap_s": MINIMUM_COMMON_OVERLAP_S,
            "maximum_normalized_linear_slope_spread_hz_s": MAXIMUM_NORMALIZED_SLOPE_SPREAD_HZ_S,
            "claim": "descriptive physical screen only",
        },
        "summary": {
            "capture_count": len(enriched),
            "analysis_run_count": len(enriched),
            "lane_counts": dict(sorted(lane_counts.items())),
            "category_counts": dict(sorted(category_counts.items())),
            "stream_count": stream_count,
            "continuity_clean_stream_count": clean_stream_count,
            "maximum_queue_high_water_refills": maximum_queue_high_water,
            "maximum_refill_service_interval_ns": maximum_refill_interval_ns,
            "product_status_counts": dict(sorted(product_status_counts.items())),
            "json_product_hash_audit_performed": args.hash_json_products,
            "json_product_count": json_product_count,
            "json_product_bytes": json_product_bytes,
            "json_product_error_count": len(json_product_errors),
        },
        "captures": enriched,
    }
    (output_directory / "retrospective-data.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    _write_csv(enriched, output_directory / "capture-analysis-inventory.csv")
    _write_markdown(enriched, output_directory / "CAPTURE_AND_ANALYSIS_IDS.md")


if __name__ == "__main__":
    main()
