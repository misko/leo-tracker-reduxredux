"""Development composition: fast GLRT -> existing deployed TrackingInput/service.

Run `glrt` in the owned scientific environment and `standard` in the explicitly
selected deployed worker environment. No reference checkout or copied scientific
implementation is imported. Outputs use the existing tracking store and schemas.
"""
import argparse
import json
import time
from pathlib import Path


def load_tracking_input(document):
    from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
    from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1

    source = dict(document["source"])
    anchor = document["clock_anchor"]
    clocks = document["delivery_clocks"]
    if anchor is not None:
        if not clocks or anchor["sample_counter"] > min(
            (p["valid_start_counter"] for p in source["probes"]),
            default=anchor["sample_counter"]):
            raise ValueError("UTC bracket does not cover the tracking input")
        offsets = [c["realtime_ns"] - c["monotonic_ns"] for c in clocks]
        offsets += [anchor["before"]["realtime_ns"] - anchor["before"]["monotonic_ns"]]
        if max(offsets) - min(offsets) > 2_000_000_000:
            raise ValueError("capture clock step exceeds association policy")
        source["timing"] = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
            session_id=source["session_id"], sample_rate_hz=source["sample_rate_hz"],
            session_start_device_sample_counter=anchor["sample_counter"],
            begin_before_realtime_ns=anchor["before"]["realtime_ns"],
            begin_before_monotonic_ns=anchor["before"]["monotonic_ns"],
            begin_after_realtime_ns=anchor["after"]["realtime_ns"],
            begin_after_monotonic_ns=anchor["after"]["monotonic_ns"],
            terminal_realtime_ns=clocks[-1]["realtime_ns"],
            terminal_monotonic_ns=clocks[-1]["monotonic_ns"],
        )
        source["capture_start_utc_ns"] = source["timing"].first_sample_estimate_utc_ns
        source["capture_end_utc_ns"] = source["capture_start_utc_ns"] + round(
            (document["last_sample_counter"] - anchor["sample_counter"])
            * 1e9 / source["sample_rate_hz"])
    source["probes"] = tuple(TrackingProbe(**{
        **p, "candidates": tuple(TrackingCandidate(**c) for c in p["candidates"])
    }) for p in source["probes"])
    return TrackingInput(**source)


def standard(args):
    if args.full:
        return full_standard(args)
    from leo.application.scanner_tracking import ScannerTrackingService
    from leo.contracts.digests import sha256_digest
    from leo.contracts.sky import ObserverSiteV1
    from leo.operations.scanner_position import build_scan_position_diagnostic
    from leo.operations.tle_archive import TleArchiveReader
    from leo.presentation.persistent_hop_tracking import render_persistent_hop_tracking_png
    from leo.presentation.scanner_track_overlay import render_scanner_track_overlay_png
    from leo.sky.sites import resolve_preset
    from leo.storage.scanner_tracking import ScannerTrackingStore

    payload = args.input.read_bytes()
    document = json.loads(payload)
    source = load_tracking_input(document)
    class InputPort:
        def load(self, session_id):
            if session_id != source.session_id:
                raise ValueError("tracking source identity differs")
            return source
        def close(self):
            pass
    args.output.mkdir(parents=True, exist_ok=True)
    products = ScannerTrackingStore(args.output, read_only=False)
    site = resolve_preset(args.site)
    service = ScannerTrackingService(
        inputs=InputPort(), products=products, tle_archive=TleArchiveReader(args.tle_root),
        observer_site=ObserverSiteV1(latitude_deg=site.latitude_deg,
            longitude_deg=site.longitude_deg, altitude_m=site.altitude_m, label=site.label),
        renderer=render_persistent_hop_tracking_png,
        overlay_renderer=render_scanner_track_overlay_png,
        position_renderer=build_scan_position_diagnostic,
    )
    started = time.monotonic()
    print(json.dumps({"phase": "shared-tracking", "session_id": source.session_id}), flush=True)
    status = service.run(source.session_id, maximum_seconds=args.maximum_seconds,
                         group_limit=args.group_limit)
    tracking_runtime_s = time.monotonic() - started
    print(json.dumps({"phase": "shared-tracking", "state": status.state,
                      "runtime_s": time.monotonic() - started}), flush=True)
    result = status.model_dump(mode="json")
    (args.output / "standard-status.json").write_text(json.dumps(result, indent=2) + "\n")
    if status.product:
        for artifact in status.product.artifacts:
            data = products.artifact(source.session_id, artifact.name)
            if data is None or sha256_digest(data) != artifact.sha256:
                raise ValueError("standard artifact failed integrity check")
            (args.output / f"{artifact.name}.png").write_bytes(data)
    regional_result = None
    if args.regional:
        # The deployed CLI binds its input-store factory at module scope. This
        # isolated qualification process supplies the same public load/close port;
        # no deployed files, catalogue records, or numerical functions are changed.
        from unittest.mock import patch

        from leo.cli import regional_position
        from leo.storage.regional_position_v3 import B7Store
        print(json.dumps({"phase": "regional-position", "session_id": source.session_id}),
              flush=True)
        with patch.object(regional_position, "ScannerTrackingInputStore", lambda root: InputPort()):
            regional_result = regional_position.run_regional_position_analysis(
                args.output, args.tle_root, source.session_id,
                maximum_seconds=args.maximum_seconds)
        regional_store = B7Store(args.output)
        regional_status = regional_store.status(source.session_id)
        (args.output / "regional-status.json").write_text(
            regional_status.model_dump_json(indent=2) + "\n")
        png = regional_store.artifact(source.session_id, "V16")
        if png is not None:
            (args.output / "regional-position.png").write_bytes(png)
    import inspect
    receipt = {
        "input_sha256": sha256_digest(payload), "provenance": document["provenance"],
        "runtime_s": time.monotonic() - started, "service": inspect.getfile(ScannerTrackingService),
        "tracking_runtime_s": tracking_runtime_s,
        "analysis_complete": status.state == "complete" and (
            not args.regional or regional_result["state"] == "complete"),
        "timing": None if source.timing is None else source.timing.model_dump(mode="json"),
        "scope": "existing shared tracking, TLE comparison, conditional position diagnostic",
        "regional_positioning": regional_result,
    }
    (args.output / "adapter-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    with (args.output / "runtime-slices.jsonl").open("a") as stream:
        stream.write(json.dumps(receipt) + "\n")
    print(json.dumps({"tracking_state": status.state,
                      "regional_state": regional_result["state"] if regional_result else None,
                      "analysis_complete": receipt["analysis_complete"],
                      "runtime_s": time.monotonic() - started,
                      "session_id": source.session_id}), flush=True)


def full_standard(args):
    """Supply the tracking input port to the unchanged deployed standard CLI."""
    import sys
    from unittest.mock import patch

    from leo.cli import scanner_tracking
    from leo.cli.adaptive_tle_position import adaptive_tle_position_complete
    from leo.cli.blind_regional import blind_regional_complete
    from leo.cli.regional_position import regional_position_complete
    from leo.cli.scan_position_methods import (
        REFERENCE,
        position_methods_complete,
        reference_error_m,
    )
    from leo.storage.scanner_tracking import ScannerTrackingStore
    from leo.storage.scanner_tracking_source import (
        ScannerTrackingInputStore,
        TrackingSourceMetadata,
    )

    document = json.loads(args.input.read_bytes())
    source = load_tracking_input(document)
    original_load = ScannerTrackingInputStore.load
    original_captured = ScannerTrackingInputStore.captured_at
    original_history = ScannerTrackingInputStore.history_metadata

    def load(store, session_id):
        return source if session_id == source.session_id else original_load(store, session_id)

    def captured(store, session_id):
        return (source.capture_start_utc_ns if session_id == source.session_id
                else original_captured(store, session_id))

    def history(store):
        return (*original_history(store), TrackingSourceMetadata(source.session_id,
            source.capture_start_utc_ns, source.capture_start_utc_ns, source.radio_id))

    command = ["scanner_tracking", "--bulk-root", str(args.output), "--tle-root",
        str(args.tle_root), "--site", args.site, "--session-id", source.session_id,
        "--maximum-seconds", str(args.maximum_seconds), "--maximum-sessions", "1",
        "--queue-worker"]
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with patch.object(ScannerTrackingInputStore, "load", load), \
         patch.object(ScannerTrackingInputStore, "captured_at", captured), \
         patch.object(ScannerTrackingInputStore, "history_metadata", history), \
         patch.object(sys, "argv", command):
        scanner_tracking.main()
    expected = {"expected_input_manifest_sha256": source.input_manifest_sha256}
    both = {"expected_input": source.input_manifest_sha256,
            "expected_analysis": source.analysis_manifest_sha256}
    stages = {
        "tracking": ScannerTrackingStore(args.output).analysis_status(source.session_id).state
                    == "complete",
        "position_methods": position_methods_complete(args.output, source.session_id, **expected),
        "blind_regional": blind_regional_complete(args.output, source.session_id, **expected),
        "adaptive_tle_position": adaptive_tle_position_complete(
            args.output, source.session_id, **both),
        "regional_position": regional_position_complete(args.output, source.session_id, **both),
    }
    receipt_root = args.receipt_root or args.output
    receipt_root.mkdir(parents=True, exist_ok=True)
    if stages["regional_position"]:
        from leo.analysis.regional_position_score import coordinates
        from leo.contracts.regional_position import RegionalPrior
        from leo.storage.regional_position_v3 import B7Store

        regional = B7Store(args.output).status(source.session_id).manifest.document
        rows = []
        for stage in ("B3", "B4", "B4W"):
            attempts = regional.diagnostics.get("b7", {}).get("attempts", {}).get(stage, {})
            for arm, fit in attempts.items():
                lat, lon = coordinates(RegionalPrior(), fit["vector"][:2])
                rows.append({"stage": stage, "arm": arm, "objective": fit["objective"],
                    "posterior_rms_hz": fit["posterior_rms_hz"],
                    "reference_distance_m": reference_error_m(lat, lon, REFERENCE),
                    "coefficient_hz_per_ghz": fit["vector"][6], "converged": fit["converged"]})
        (receipt_root / "controlled-c-ablation.json").write_text(json.dumps({
            "scope": "Matched within each stage before RF-time terms; shared upstream fitted-c "
                     "calibration and association. In-sample fit and reference error are separate.",
            "rows": rows}, indent=2) + "\n")
    receipt = {"session_id": source.session_id, "analysis_complete": all(stages.values()),
        "standard_stages": stages, "runtime_s": time.monotonic() - started,
        "provenance": document["provenance"],
        "timing": source.timing.model_dump(mode="json") if source.timing else None}
    (receipt_root / "adapter-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    with (receipt_root / "runtime-slices.jsonl").open("a") as stream:
        stream.write(json.dumps(receipt) + "\n")
    print(json.dumps(receipt), flush=True)


def glrt(args):
    from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
    from leo.processing.fast_scan import FastScanProcessing, process_recording
    from tests.postgres_support import isolated_test_schema_url
    args.output.mkdir(parents=True, exist_ok=True)
    with isolated_test_schema_url(prefix="fast_standard_e2e") as database_url:
        started = time.monotonic()
        report = process_recording(args.recording, database_url=database_url,
                                   root=args.output, workers=8)
        engine = create_catalog_engine(database_url)
        try:
            app = FastScanProcessing(CatalogRepository(create_session_factory(engine)), args.output)
            document = app.tracking_input(report["run_id"])
            (args.output / "tracking-input.json").write_text(json.dumps(document) + "\n")
        finally:
            engine.dispose()
        print(json.dumps({"run_id": report["run_id"], "counts": report["counts"],
                          "runtime_s": time.monotonic() - started}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("glrt")
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(run=glrt)
    p = commands.add_parser("standard")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--site", default="spinnaker-sausalito")
    p.add_argument("--receipt-root", type=Path)
    p.add_argument("--full", action="store_true", help="Run the existing complete standard CLI.")
    p.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    p.add_argument("--maximum-seconds", type=float, default=300)
    p.add_argument("--group-limit", type=int, default=4)
    p.add_argument("--regional", action="store_true",
                   help="Also call the existing Hard60/B7 regional pipeline and its c ablation.")
    p.set_defaults(run=standard)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
