"""Freeze currently available adaptive DS22 analysis through a read-only public port.

Run with the current same-repository storage implementation on PYTHONPATH.
This exports existing products only; it never requests acquisition or analysis.
The original sealed DS22 snapshot remains unchanged.
"""

import argparse
import dataclasses
import hashlib
import json
import time
from pathlib import Path


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def run(dataset, bulk, output, limit=None):
    import leo.storage.scanner_tracking_source as public_port
    from leo.storage.errors import BundleNotFoundError

    output.mkdir(parents=True, exist_ok=False)
    payload = (dataset / "manifest.json").read_bytes()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    seal = json.loads((dataset / "seal.json").read_text())
    if digest != seal["files"]["manifest.json"]:
        raise ValueError("original DS22 manifest seal changed")
    members = json.loads(payload)["members"]
    selected = [m for m in members if m.get("recording_format") == "starlink_adaptive_hop_iq"]
    write(
        output / "protocol.json",
        dict(
            dataset_manifest_sha256=digest,
            members=len(members),
            adaptive_members=len(selected),
            public_port="ScannerTrackingInputStore.load",
            bulk_root=str(bulk),
            port_source_sha256=hashlib.sha256(Path(public_port.__file__).read_bytes()).hexdigest(),
            export_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            adaptive_probe_stride_ms=120,
            new_acquisition=False,
            new_analysis=False,
            snapshot_mode="new public-port products; original sealed snapshot retained",
        ),
    )
    ledger = [
        dict(source_id=m["dataset_label"], session_id=m["recording_id"], status="pending")
        for m in selected
    ]
    store = public_port.ScannerTrackingInputStore(bulk, adaptive_probe_stride_ms=120)
    try:
        for number, member in enumerate(selected):
            if limit is not None and number >= limit:
                break
            row = ledger[number]
            started = time.monotonic()
            try:
                tracking = store.load(member["recording_id"])
                if (
                    tracking.capture_mode != "adaptive"
                    or tracking.session_id != member["recording_id"]
                ):
                    raise ValueError("public port returned wrong capture identity or mode")
                doc = dataclasses.asdict(tracking)
                doc["timing"] = tracking.timing.model_dump(mode="json") if tracking.timing else None
                folder = output / member["dataset_label"]
                folder.mkdir()
                write(folder / "tracking.json", doc)
                row.update(
                    status="exported",
                    probes=len(tracking.probes),
                    qualified=tracking.qualified,
                    input_manifest_sha256=tracking.input_manifest_sha256,
                    analysis_manifest_sha256=tracking.analysis_manifest_sha256,
                    raw_recording_authority_digest=tracking.raw_recording_authority_digest,
                    snapshot_sha256=hashlib.sha256(
                        (folder / "tracking.json").read_bytes()
                    ).hexdigest(),
                    timing_available=tracking.timing is not None,
                )
            except BundleNotFoundError as exc:
                row.update(status="existing_analysis_unavailable", reason=str(exc))
            except (ValueError, OSError) as exc:
                row.update(status="invalid_or_unreadable_existing_product", reason=str(exc))
            row["elapsed_seconds"] = time.monotonic() - started
            write(output / "coverage.json", ledger)
            print(json.dumps(row), flush=True)
    finally:
        store.close()
    write(output / "coverage.json", ledger)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    qnap = Path("/mnt/qnap01")
    if args.output.resolve() == qnap or qnap in args.output.resolve().parents:
        parser.error("QNAP is read-only")
    run(args.dataset, args.bulk_root, args.output, args.limit)
