"""Read-only, fixed-window audit of adaptive capture, analysis, and served figures."""

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.scanner_tracking import ScannerTrackingStore


def verify_png(base, path, digest, expected_size=None):
    try:
        with urlopen(base + path, timeout=45) as response:
            data = response.read()
            content_type = response.headers.get_content_type()
        with Image.open(BytesIO(data)) as image:
            size = image.size
            image.verify()
        assert content_type == "image/png", content_type
        assert "sha256:" + sha256(data).hexdigest() == digest, "digest mismatch"
        assert expected_size is None or size == expected_size, size
        return {"path": path, "sha256": digest, "size": size, "verified": True}
    except Exception as error:
        return {"path": path, "verified": False, "error": str(error)}


def audit_one(root, base, sid):
    captures = AdaptiveHopIqStore(root, read_only=True)
    try:
        capture = captures.inspect(sid)
        receipt = capture.manifest.receipt
        status = AdaptiveHopAnalysisPresentationStore(root).status_for_capture(
            capture, probe_stride_ms=120
        )
        tracking = ScannerTrackingStore(root, read_only=True).analysis_status(sid)
        row = {
            "session_id": sid,
            "created_utc_ns": capture.manifest.created_utc_ns,
            "sample_rate_hz": receipt.plan.geometry.sample_rate_hz,
            "receiver_ids": receipt.plan.geometry.receiver_ids,
            "radio_serial": receipt.radio_serial,
            "capture_digest": capture.manifest_sha256,
            "valid_duty_pct": receipt.valid_duty_ppm / 10000,
            "valid_seconds": receipt.valid_sample_count / receipt.plan.geometry.sample_rate_hz,
            "terminal": receipt.terminal.model_dump(mode="json"),
            "metrics": status.model_dump(mode="json"),
            "tracking": tracking.model_dump(mode="json"),
            "artifacts": [],
            "problems": [],
        }
        lanes = Counter()
        for event in receipt.events:
            target = event.target
            if target is not None:
                lanes[f"CH{target.channel}{target.edge.value}"] += 1
        row["visit_lanes"] = dict(lanes)
        paths = [
            (f"/api/v3/scanner/adaptive-sessions/{sid}/analysis?probe_stride_ms=120", "metrics")
        ]
        if tracking.state == "complete":
            paths.append((f"/api/v1/scanner/tracking/{sid}", "tracking"))
        for path, name in paths:
            try:
                with urlopen(base + path, timeout=45) as response:
                    payload = json.load(response)
                if name == "tracking":
                    assert payload["product"] == row["tracking"]["product"], "tracking JSON differs"
                else:
                    assert payload["input_manifest_sha256"] == capture.manifest_sha256
                    assert payload["metrics_manifest_sha256"] == status.metrics_manifest_sha256
                row[name + "_json_verified"] = True
            except Exception as error:
                row["problems"].append(f"{name} JSON: {error}")
        if status.overview:
            for artifact in status.overview.artifacts:
                query = urlencode(
                    {
                        "binding_sha256": status.binding_sha256,
                        "artifact_sha256": artifact.sha256,
                        "probe_stride_ms": 120,
                    }
                )
                row["artifacts"].append(
                    verify_png(
                        base,
                        f"/api/v1/scanner/adaptive-sessions/{sid}/analysis/{artifact.name}.png?{query}",
                        artifact.sha256,
                    )
                )
        product = tracking.product
        if product:
            if product.input_manifest_sha256 != capture.manifest_sha256:
                row["problems"].append("tracking capture binding stale")
            if product.analysis_manifest_sha256 != status.metrics_manifest_sha256:
                row["problems"].append("tracking metrics binding stale")
            reviews = {r.artifact_name for r in product.track_reviews}
            artifacts = {a.name for a in product.artifacts if a.name.startswith("tle-review-")}
            if reviews != artifacts:
                row["problems"].append("track review/PNG inventory mismatch")
            for artifact in product.artifacts:
                row["artifacts"].append(
                    verify_png(
                        base,
                        f"/api/v1/scanner/tracking/{sid}/{artifact.name}.png?"
                        + urlencode({"sha256": artifact.sha256}),
                        artifact.sha256,
                        (2250, 2100) if artifact.name.startswith("tle-review-") else None,
                    )
                )
        row["problems"].extend(a["error"] for a in row["artifacts"] if not a["verified"])
        return row
    except Exception as error:
        return {"session_id": sid, "problems": [f"{type(error).__name__}: {error}"]}
    finally:
        captures.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--until-ns", type=int, required=True)
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    args = parser.parse_args()
    start = args.until_ns - args.hours * 3600 * 10**9
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        ids = [sid for ts, sid in store.publication_index() if start <= ts <= args.until_ns]
    finally:
        store.close()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(lambda sid: audit_one(args.bulk_root, args.base_url, sid), ids):
            results.append(row)
            (args.output / (row["session_id"] + ".json")).write_text(
                json.dumps(row, indent=2) + "\n"
            )
            if len(results) % 20 == 0:
                print(json.dumps({"audited": len(results), "total": len(ids)}), flush=True)
    summary = {
        "start_ns": start,
        "end_ns": args.until_ns,
        "audited_at": datetime.now(UTC).isoformat(),
        "sessions": len(results),
        "metrics_states": dict(
            Counter(r.get("metrics", {}).get("state", "error") for r in results)
        ),
        "tracking_states": dict(
            Counter(r.get("tracking", {}).get("state", "error") for r in results)
        ),
        "verified_pngs": sum(a["verified"] for r in results for a in r.get("artifacts", [])),
        "problems": {r["session_id"]: r["problems"] for r in results if r["problems"]},
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
