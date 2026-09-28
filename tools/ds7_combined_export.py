#!/usr/bin/env python3
"""Run unchanged DS7 track and bank exporters with one public input preparation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from contextlib import contextmanager
from pathlib import Path


def _normalized_json(path: Path, ignored: tuple[str, ...]) -> dict:
    value = json.loads(path.read_text())
    for key in ignored:
        value.pop(key, None)
    return value


def compare_science_outputs(
    reference_tracks: Path,
    reference_banks: Path,
    combined_tracks: Path,
    combined_banks: Path,
) -> dict:
    """Fail unless all scientific JSON fields and NPZ arrays are exactly equal."""
    import numpy as np

    reference_manifest = json.loads((reference_banks / "manifest.json").read_text())
    combined_manifest = json.loads((combined_banks / "manifest.json").read_text())
    reference_track_digest = "sha256:" + hashlib.sha256(reference_tracks.read_bytes()).hexdigest()
    combined_track_digest = "sha256:" + hashlib.sha256(combined_tracks.read_bytes()).hexdigest()
    if reference_manifest.get("tracks_sha256") != reference_track_digest:
        raise ValueError("reference bank manifest does not bind its track file")
    if combined_manifest.get("tracks_sha256") != combined_track_digest:
        raise ValueError("combined bank manifest does not bind its track file")
    tracks_equal = _normalized_json(reference_tracks, ("elapsed_seconds",)) == _normalized_json(
        combined_tracks, ("elapsed_seconds",)
    )
    shortlists_equal = _normalized_json(
        reference_banks / "shortlists.json", ()
    ) == _normalized_json(combined_banks / "shortlists.json", ())
    manifest_equal = _normalized_json(
        reference_banks / "manifest.json", ("elapsed_seconds", "tracks_sha256")
    ) == _normalized_json(
        combined_banks / "manifest.json", ("elapsed_seconds", "tracks_sha256")
    )
    with np.load(reference_banks / "banks.npz") as reference, np.load(
        combined_banks / "banks.npz"
    ) as combined:
        keys_equal = set(reference.files) == set(combined.files)
        unequal = (
            sorted(
                key
                for key in reference.files
                if reference[key].dtype != combined[key].dtype
                or not np.array_equal(reference[key], combined[key])
            )
            if keys_equal
            else sorted(set(reference.files) ^ set(combined.files))
        )
        array_count = len(reference.files)
    if not tracks_equal or not shortlists_equal or not manifest_equal or unequal:
        raise ValueError("combined export differs from reference scientific outputs")
    return {
        "tracks_equal_ignoring_elapsed": tracks_equal,
        "shortlists_exactly_equal": shortlists_equal,
        "manifest_equal_ignoring_elapsed_and_tracks_hash": manifest_equal,
        "array_keys_equal": keys_equal,
        "array_values_exactly_equal": not unequal,
        "array_count": array_count,
        "reference_tracks_sha256": reference_track_digest,
        "combined_tracks_sha256": combined_track_digest,
    }


def _load_exporter():
    path = Path(__file__).with_name("ds7_export_baseline.py")
    spec = importlib.util.spec_from_file_location("ds7_export_baseline_combined", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the baseline exporter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _reuse_hooks(
    tracking_module,
    preparation_module,
    *,
    session: str,
    bulk_root: Path,
    raw,
    prepared,
):
    """Temporarily replace only the two repeated public operations."""
    original_store = tracking_module.ScannerTrackingInputStore
    original_prepare = preparation_module.prepare_adaptive_tle_position_inputs
    calls = {"store_construct": 0, "load": 0, "prepare": 0, "close": 0}

    class CachedInputStore:
        def __init__(self, root):
            calls["store_construct"] += 1
            if Path(root) != bulk_root:
                raise ValueError("combined exporter bulk root changed")

        def load(self, requested_session):
            calls["load"] += 1
            if requested_session != session:
                raise ValueError("combined exporter session changed")
            return raw

        def close(self):
            calls["close"] += 1

    def cached_prepare(requested_session, *, inputs, archive):
        del archive
        calls["prepare"] += 1
        if requested_session != session or inputs.load(requested_session) is not raw:
            raise ValueError("combined preparation input changed")
        return prepared

    tracking_module.ScannerTrackingInputStore = CachedInputStore
    preparation_module.prepare_adaptive_tle_position_inputs = cached_prepare
    try:
        yield calls
    finally:
        tracking_module.ScannerTrackingInputStore = original_store
        preparation_module.prepare_adaptive_tle_position_inputs = original_prepare


def combined_export(
    capture: dict,
    tracks_output: Path,
    banks_output: Path,
    bulk_root: Path,
    tle_root: Path,
) -> dict:
    """Load and prepare once, then invoke both unchanged scientific exporters."""
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.operations import adaptive_tle_position_inputs as preparation_module
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage import scanner_tracking_source as tracking_module

    exporter = _load_exporter()
    started = time.monotonic()
    session = capture["session_id"]
    source_started = time.monotonic()
    source_store = ScannerTrackingInputStore(bulk_root)
    try:
        raw = source_store.load(session)
        if raw.input_manifest_sha256 != capture["manifest_sha256"]:
            raise ValueError("source manifest mismatch")

        class Inputs:
            def load(self, requested_session):
                if requested_session != session:
                    raise ValueError("unexpected session")
                return raw

        prepared = prepare_adaptive_tle_position_inputs(
            session,
            inputs=Inputs(),
            archive=TleArchiveReader(tle_root),
        )
        source_seconds = time.monotonic() - source_started
        with _reuse_hooks(
            tracking_module,
            preparation_module,
            session=session,
            bulk_root=bulk_root,
            raw=raw,
            prepared=prepared,
        ) as reuse_calls:
            tracks = exporter.export(capture, tracks_output, bulk_root, tle_root)
            banks = exporter.export_banks(
                capture, tracks_output, banks_output, bulk_root, tle_root
            )
    finally:
        source_store.close()
    return {
        "schema": "ds7-combined-export-receipt/v1",
        "session_id": session,
        "manifest_sha256": capture["manifest_sha256"],
        "source_load_and_prepare_seconds": source_seconds,
        "tracks_reported_seconds": tracks["elapsed_seconds"],
        "banks_reported_seconds": banks["elapsed_seconds"],
        "total_seconds": time.monotonic() - started,
        "reused_operations": reuse_calls,
        "tracks": len(tracks["tracks"]),
        "bank_tracks": len(banks["tracks"]),
        "science_implementation": "unchanged tools/ds7_export_baseline.py",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--tracks-output", type=Path, required=True)
    parser.add_argument("--banks-output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--reference-tracks", type=Path)
    parser.add_argument("--reference-banks", type=Path)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    rows = [row for row in plan["captures"] if row["session_id"] == args.session]
    if len(rows) != 1:
        raise ValueError("session absent or duplicated in plan")
    if (args.reference_tracks is None) != (args.reference_banks is None):
        raise ValueError("reference tracks and banks must be supplied together")
    result = combined_export(
        rows[0], args.tracks_output, args.banks_output, args.bulk_root, args.tle_root
    )
    if args.reference_tracks is not None:
        result["equivalence"] = compare_science_outputs(
            args.reference_tracks,
            args.reference_banks,
            args.tracks_output,
            args.banks_output,
        )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
