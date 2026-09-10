"""Read-only verification of one published .21 capture through component ports.

Run with the deployed release Python as leo. OUTPUT must be a new local path.
This never opens a radio, starts analysis, or changes persisted capture products.
"""

import argparse
import gzip
import hashlib
import json
import time
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.persistent_hop import PersistentHopIqStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("fixed", "adaptive"))
    parser.add_argument("session_id")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute() or str(args.output).startswith("/mnt/qnap01"):
        parser.error("output must be an absolute local path outside QNAP")
    args.output.mkdir(parents=True, exist_ok=False)
    store = (
        AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
        if args.kind == "adaptive"
        else PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    )
    started = time.monotonic()
    try:
        capture = store.verify(args.session_id)
        manifest = capture.manifest
        receipt = manifest.receipt
        assert receipt.radio_id == "radio_pluto_19f2"
        assert receipt.radio_serial == "10400056f695001322002d0010ad1719f2"
        assert receipt.radio_uri == "ip:192.168.1.21:30432"
        geometry = receipt.plan.geometry if args.kind == "adaptive" else receipt.plan
        rate = geometry.sample_rate_hz
        seconds = receipt.duty_denominator_sample_count / rate
        assert 300 <= seconds < 301
        assert receipt.valid_duty_ppm >= 900000
        assert geometry.bandwidth_hz == rate
        assert geometry.valid_visit_ms == 120
        assert receipt.restoration.status == "restored"
        if args.kind == "adaptive":
            assert receipt.terminal.state == "completed"
            visits = receipt.complete_visit_count
        else:
            assert receipt.capture_outcome == "complete"
            assert receipt.continuity_attested and receipt.qualified
            visits = len(receipt.visits)
        with gzip.open(args.output / "manifest.json.gz", "wb") as stream:
            stream.write(manifest.model_dump_json().encode())
        summary = dict(
            verified_at=datetime.now(UTC).isoformat(),
            kind=args.kind,
            session_id=args.session_id,
            radio_id=receipt.radio_id,
            radio_serial=receipt.radio_serial,
            radio_uri=receipt.radio_uri,
            sample_rate_hz=rate,
            bandwidth_hz=geometry.bandwidth_hz,
            source_seconds=seconds,
            valid_iq_seconds=receipt.valid_sample_count / rate,
            valid_duty_percent=receipt.valid_duty_ppm / 10000,
            complete_visits=visits,
            full_iq_verified=True,
            verify_seconds=time.monotonic() - started,
            input_manifest_sha256=capture.manifest_sha256,
            restoration="restored",
            compressed_bytes=manifest.compressed_bytes,
            uncompressed_bytes=manifest.uncompressed_bytes,
        )
        route = "adaptive-sessions" if args.kind == "adaptive" else "persistent-sessions"
        url = f"http://127.0.0.1:8090/api/v1/scanner/{route}/{args.session_id}/glrt"
        with urllib.request.urlopen(url, timeout=20) as response:
            publication = json.load(response)
        with gzip.open(args.output / "glrt-publication.json.gz", "wb") as stream:
            stream.write(json.dumps(publication).encode())
        evidence = publication.get("evidence") or {}
        results = evidence.get("results", [])
        summary["glrt"] = {key: value for key, value in evidence.items() if key != "results"}
        summary["glrt"]["result_count"] = len(results)
        summary["glrt"]["verdict_counts"] = dict(Counter(item["verdict"] for item in results))
        summary["glrt"]["window_masks"] = dict(
            Counter(item["search_window_mask"] for item in results)
        )
        if results:
            summary["glrt"]["wall_ms_quantiles"] = dict(
                zip(
                    ("median", "p95", "p99", "max"),
                    np.quantile(
                        [item["wall_ms"] for item in results], (0.5, 0.95, 0.99, 1)
                    ).tolist(),
                    strict=True,
                )
            )
        summary["classification_warning"] = publication["error"]
        summary["evidence_files"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in args.output.iterdir()
            if path.is_file()
        }
        with (args.output / "verification.json").open("x") as stream:
            json.dump(summary, stream, indent=2)
            stream.write("\n")
        print(json.dumps(summary))
    finally:
        if args.kind == "adaptive":
            store.close()


if __name__ == "__main__":
    main()
