"""Analyze one sealed fast recording using two-scan cancellation and a supplied search area."""

import argparse
import fcntl
import json
import os
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.contracts.fast_standard_analysis import ALGO08V2
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.fast_standard_analysis import render
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastScanStore, FastSegmentSource, immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.algo08_position import solve
from tools.pipeline_eval.qualification.blind_compact_run import detector

# Qualified x86-64 Gauss release, including both possible pilot edges.
PINS = {
    "cancellation-factors.so": "f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809",
    "lower.f32": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
    "upper.f32": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c",
    "tracks.json": "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a",
}


def acquire(session, inventory_sha, inventory, assets):
    policy = FastScanPolicyV2()
    probes, clocks, hashes, excluded, anchors = [], [], [], [], []
    authorities = set()
    previous_end = generation = edge = None
    with ExitStack() as stack:
        for entry in inventory["segments"]:
            segment = FastSegmentSource(entry)
            receivers = tuple(segment.receiver_ids)
            if receivers != (0, 1) or segment.reader.manifest.sample_rate_hz != 10_000_000:
                raise ValueError("ALGO08 requires native dual-antenna 10 MS/s recordings")
            for w in segment.windows():
                a, t, visit = w.acquisition, w.target, len(hashes)
                if edge is None:
                    edge = t["edge"]
                    receiver = stack.enter_context(detector("cancellation", edge,
                        binary=assets/"cancellation-factors.so", pilot=assets/(edge+".f32")))
                    generation = a["generation"]
                if (type(generation) is not int or edge != t["edge"] or a["global_visit"] != visit or a["generation"] != generation
                        or previous_end is not None and a["sample_start"] < previous_end):
                    raise ValueError("RF edge, visit order or stream generation changed")
                previous_end = a["sample_end"]
                receipt = json.loads(a["retune_receipt"])
                clocks.append(receipt["host_delivery_clock"])
                if receipt.get("utc_clock_bracket") is not None:
                    if visit or receipt["utc_clock_bracket"]["sample_counter"] != a["sample_start"]:
                        raise ValueError("Invalid hardware clock anchor")
                    anchors.append(receipt["utc_clock_bracket"])
                hashes.append(w.iq_sha256)
                authorities.add(t.get("rf_mapping_authority", "unknown"))
                if valid_window_support(a, w.sample_rate_hz, w.samples.shape, receivers, policy):
                    probes.extend(receiver(SimpleNamespace(acquisition=a, target=t, samples=w.samples,
                                              sample_rate_hz=w.sample_rate_hz, receiver_ids=receivers)))
                else:
                    excluded.append(dict(visit=visit, sample_start=a["sample_start"], sample_end=previous_end,
                                         iq_sha256=w.iq_sha256, reason="invalid sample support or retune quality"))
    if len(hashes) != inventory["window_count"] or len(anchors) != 1:
        raise ValueError("Incomplete recording traversal or missing initial clock")
    raw = canonical_digest([inventory_sha, hashes])
    detection = canonical_digest(["cancellation", raw, PINS["cancellation-factors.so"], probes])
    return dict(schema_version=2, clock_anchor=anchors[0], delivery_clocks=clocks,
                last_sample_counter=previous_end, source=dict(session_id=session, capture_mode="adaptive",
                    sample_rate_hz=policy.sample_rate_hz, radio_id=segment.radio["serial"],
                    stream_generation=f"continuous-iio-{generation:016x}", input_manifest_sha256=inventory_sha,
                    analysis_manifest_sha256=detection, raw_recording_authority_digest=raw, qualified=True,
                    timing=None, probes=probes, probe_ms=20, capture_start_utc_ns=None, capture_end_utc_ns=None),
                provenance=dict(run_id="blind-compact-"+detection[7:39], scope="cancellation",
                    detector_sha256="sha256:"+PINS["cancellation-factors.so"], window_count=len(hashes),
                    processed_windows=len(probes)//2, invalid_capture=len(excluded), excluded_windows=excluded,
                    skipped_fast_score=0, rf_mapping_authorities=sorted(authorities)))


def scan_report(recording, run_id, native):
    source, provenance = native["source"], native["provenance"]
    policy = FastScanPolicyV2()
    channels, points = {}, []
    for p in source["probes"]:
        key = p["channel"], p["receiver_id"]
        row = channels.setdefault(key, dict(channel=key[0], receiver_id=key[1], processed=0,
                                            skipped=0, active=0, strong=0))
        row["processed"] += 1
        for c in p["candidates"]:
            margin = c["fractional_margin"]
            row["active"] += 1
            row["strong"] += int(margin >= policy.strong_margin)
            points.append(dict(visit=p["visit_index"], channel=key[0], receiver_id=key[1], score=None,
                               cfo_hz=c["fractional_tracking_cfo_hz"], margin=margin,
                               time_s=(p["valid_start_counter"]-native["clock_anchor"]["sample_counter"])
                                      / policy.sample_rate_hz))
    return dict(schema_version=1, kind="fast-scan.report", model_version=ALGO08V2, run_id=run_id,
                recording_name=recording, session_id=source["session_id"], policy=policy.model_dump(),
                rf_mapping_authorities=provenance["rf_mapping_authorities"], time_basis="relative sample counter",
                qualified_tracking=True, channels=[channels[k] for k in sorted(channels)], points=points,
                window_count=provenance["window_count"], counts=dict(processed=provenance["processed_windows"],
                    invalid_capture=provenance["invalid_capture"], skipped_fast_score=0))


def analyze(recording, root, assets, archive, offer, reference=None, *, list_report=True):
    if reference is not None:
        lat, lon = reference["latitude_deg"], reference["longitude_deg"]
        if not (-90 <= lat <= 90 and -180 <= lon < 180):
            raise ValueError("Invalid evaluation reference")
    for name, pin in PINS.items():
        if sha256_digest((assets/name).read_bytes()) != "sha256:"+pin:
            raise ValueError(f"Unqualified ALGO08 asset {name}")
    store, standard = FastScanStore(root), FastStandardAnalysisStore(root)
    session, inventory_sha, inventory = store.inventory(recording, verify_windows=False)
    detector_id = "algo08-v2-" + canonical_digest([ALGO08V2, inventory_sha])[7:39]
    run_id = "algo08-v2-" + canonical_digest([ALGO08V2, inventory_sha, offer.document(), reference])[7:39]
    detector_work = store.automatic_workspace(detector_id)
    with (detector_work/"owner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = detector_work/"detections.json"
        if not path.exists():
            immutable_json(path, acquire(session, inventory_sha, inventory, assets))
        native = json.loads(path.read_bytes())
        if native["source"]["input_manifest_sha256"] != inventory_sha:
            raise ValueError("Saved detections belong to another acquisition")
        bound = native["source"]
        if (bound["session_id"] != session or
            bound["analysis_manifest_sha256"] != canonical_digest(["cancellation",
                bound["raw_recording_authority_digest"], PINS["cancellation-factors.so"], bound["probes"]])):
            raise ValueError("Saved two-scan factors differ from the acquisition receipt")
        store.publish_inventory(session, inventory)
    workspace = store.automatic_workspace(run_id)
    with (workspace/"owner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = standard.detail(run_id)
        if result["state"] == "pending":
            prediction, packet, policy = solve(native, TleArchiveReader(archive), assets, offer)
            terminal = dict(model_version=ALGO08V2, session_id=session, orbit_policy=policy, region=offer.document(),
                            decision=prediction["status"], reason=prediction.get("reason"),
                            arms=prediction["arms"], native_sha256=canonical_digest(native))
            immutable_json(workspace/"terminal.json", terminal)
            binding = dict(session_id=session, input_sha256=terminal["native_sha256"],
                           raw_authority=native["source"]["raw_recording_authority_digest"],
                           terminal_sha256=canonical_digest(terminal), orbit_policy=policy, region=offer.document())
            if prediction["status"] == "withheld":
                result = standard.withhold(run_id, prediction["reason"], **binding)
            elif prediction["status"] == "ok" and packet is not None:
                pngs = render(packet, title=recording.name, evaluation_reference=reference)
                doc = dict(**binding, run_id=run_id, schema_version=3, model_version=ALGO08V2,
                           state="complete", selected_model=ALGO08V2, figures_model=ALGO08V2,
                           reference_usage="evaluation_only", decision="compact_v5",
                           arms=packet["arms"], glrt_points=len(packet["observations"]),
                           objective_replay=packet["objective_replay"])
                result = standard.publish(run_id, doc, pngs, position_grid=packet["position_grid"],
                                          position_path=packet["position_path"])
            else:
                raise RuntimeError("Compact solver did not return a scientific decision")
        if reference and result["state"] == "complete":
            standard.set_evaluation_reference(run_id, reference["latitude_deg"], reference["longitude_deg"])
        for figure in result["artifacts"]:
            standard.artifact(run_id, figure["name"], figure["sha256"])
        report = scan_report(recording.name, run_id, native)
        if list_report:
            store.publish(run_id, report)
        return dict(run_id=run_id, session_id=session, window_count=report["window_count"],
                    counts=report["counts"], region=offer.document(), decision=result["state"],
                    terminal_sha256=result["terminal_sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--region", type=Path, required=not os.getenv("ALGO08_REGION_FILE"),
                        help="JSON with center [latitude, longitude], width_km and optional screen_center")
    parser.add_argument("--evaluation-reference", type=float, nargs=2, metavar=("LAT", "LON"))
    parser.add_argument("--comparison-only", action="store_true")
    args = parser.parse_args(argv)
    reference = args.evaluation_reference
    # An explicit search offer replaces the station context, including its annotation.
    if args.region is None and reference is None:
        station = [os.getenv("ALGO08_EVALUATION_LATITUDE"), os.getenv("ALGO08_EVALUATION_LONGITUDE")]
        if any(v is not None for v in station):
            if None in station:
                parser.error("Station scoring requires both evaluation coordinates")
            reference = list(map(float, station))
    ref = dict(zip(("latitude_deg", "longitude_deg"), reference)) if reference else None
    region_path = args.region or Path(os.environ["ALGO08_REGION_FILE"])
    offer = Algo08Region.parse(json.loads(region_path.read_bytes()))
    print(json.dumps(analyze(args.recording, args.bulk_root, args.assets, args.archive, offer, ref,
                             list_report=not args.comparison_only)))


if __name__ == "__main__":
    main()
