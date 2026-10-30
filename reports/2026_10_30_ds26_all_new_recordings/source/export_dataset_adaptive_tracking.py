#!/usr/bin/env python3
"""Export public adaptive tracking contracts for a frozen dataset, without IQ."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def export_document(source, row: dict) -> dict:
    """Require the public source to bind the frozen capture and analysis."""
    expected = row["glrt_availability"]
    for key in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(source, key) != expected[key]:
            raise ValueError("public source disagrees with frozen " + key)
    if source.session_id != row["session_id"] or source.capture_mode != "adaptive":
        raise ValueError("public source has a different acquisition identity or mode")
    value = asdict(source)
    value["timing"] = source.timing.model_dump(mode="json") if source.timing else None
    return value


def main(args):
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    manifest_raw = args.manifest.read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        args.output.resolve() == Path("/mnt/qnap01")
        or Path("/mnt/qnap01") in args.output.resolve().parents
    ):
        raise ValueError("exports must be local")
    if (args.output / "input-map.json").exists():
        raise ValueError("refusing to overwrite frozen exports")
    args.output.mkdir(parents=True, exist_ok=True)
    store = ScannerTrackingInputStore(args.root, adaptive_probe_stride_ms=120)
    rows = []
    try:
        for member in manifest["members"]:
            if member["recording_format"] != "starlink_adaptive_hop_iq":
                continue
            row = {key: member[key] for key in ("dataset_label", "case_id", "session_id")}
            if not member["glrt_availability"]["available"]:
                rows.append(
                    dict(
                        row, status="unavailable", reason=member["glrt_availability"].get("reason")
                    )
                )
                continue
            try:
                source = store.load(member["session_id"])
                value = export_document(source, member)
                path = args.output / (member["case_id"] + ".json")
                raw = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
                if path.exists():
                    if path.read_bytes() != raw:
                        raise ValueError("prior partial export changed")
                else:
                    with path.open("xb") as handle:
                        handle.write(raw)
                rows.append(
                    dict(
                        row,
                        status="exported",
                        input_path=str(path.resolve()),
                        input_sha256=digest(raw),
                        input_manifest_sha256=source.input_manifest_sha256,
                        analysis_manifest_sha256=source.analysis_manifest_sha256,
                        raw_recording_authority_digest=source.raw_recording_authority_digest,
                        probe_count=len(source.probes),
                        sample_rate_hz=source.sample_rate_hz,
                    )
                )
            except (OSError, ValueError, RuntimeError) as error:
                rows.append(
                    dict(row, status="failed", error_type=type(error).__name__, reason=str(error))
                )
            print(row["dataset_label"], rows[-1]["status"], len(rows), flush=True)
    finally:
        store.close()
    result = dict(
        schema="dataset-public-tracking-input-map/v1",
        dataset_id=manifest["dataset_id"],
        dataset_manifest_sha256=digest(manifest_raw),
        adapter="ScannerTrackingInputStore.load",
        adaptive_probe_stride_ms=120,
        exporter_sha256=digest(Path(__file__).read_bytes()),
        rows=rows,
        counts={
            status: sum(row["status"] == status for row in rows)
            for status in ("exported", "unavailable", "failed")
        },
    )
    (args.output / "input-map.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(result["counts"]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/srv/bulk/leo"))
    main(parser.parse_args())
