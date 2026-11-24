"""Compare ordinary and aperture-centroid graph time on one authenticated cached packet."""

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
CHARTED = Path("/tmp/leo-v3-integrated-original-batch")
BUILD = Path("/tmp/leo-v3-integrated-original-batch-proof01/build.json")
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
AUTHORITY = "fb8ddad37edcde83527e0a2ab913a0f02d1dd3950a313a841b7d9d82355e6628"
NATIVE = "1acd2fcf8104fe990eaf40c82848e723de2da0c74f1ac1f29f59c659442d8d0d"
CASE = "DS30-0019"
PROTOCOL = HERE / "sparse8-cfo-epoch-0019-protocol.md"
MODES = ("ordinary", "centroid")


def correction_rows(native):
    from sparse8_cfo_epoch import centroid, paired_lanes

    rows = {}
    for identity, (_, _, _, nominal, full, _, probe) in paired_lanes(native, native).items():
        eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True]
        if not eligible:
            continue
        winner = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
        shift = 0.
        if not full:
            short, _, _ = centroid(winner, True)
            long, _, _ = centroid(winner, False)
            shift = short - long
        rows[identity] = (nominal, shift, float(winner["fractional_tracking_cfo_hz"]))
    return rows


@contextmanager
def effective_graph_time(mode, native, audit, *, native_pin=NATIVE):
    from leo.analysis.localization_v3 import tracks
    from leo.contracts.digests import canonical_digest
    from sparse8_time_math import graph_rows

    original = tracks.winning_observations

    def prepare(packet):
        rows, metadata = original(packet)
        if packet is not native and canonical_digest(packet) != "sha256:" + native_pin:
            raise ValueError("Unexpected detector input at the effective-time boundary")
        if mode == "centroid":
            cpu, wall = process_time_ns(), perf_counter_ns()
            corrections = correction_rows(packet)
            rows = graph_rows(rows, corrections)
            counts = Counter(round(shift*1e6, 4) for _, shift, _ in corrections.values())
            audit["cpu_ns"] += process_time_ns()-cpu
            audit["elapsed_ns"] += perf_counter_ns()-wall
            audit["count_by_offset_us"] = dict(sorted(counts.items()))
        audit["graph_input_digests"].append(canonical_digest(rows))
        return rows, metadata

    with patch.object(tracks, "winning_observations", prepare):
        yield


def deny_backing(event, args):
    if event != "open" or not isinstance(args[0], (str, bytes)):
        return
    path = Path(os.path.abspath(os.fsdecode(args[0])))
    if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01") or path.name.endswith(".ci16.zst"):
        raise ValueError(f"Saved-only job refuses original data access: {path}")


def worker(mode, stage, *, verify_only=False, case=CASE, authority_pin=AUTHORITY, native_pin=NATIVE, protocol=PROTOCOL):
    started = process_time_ns(), perf_counter_ns()
    sys.path[:0] = [str(CHARTED / "reports/ALGO08/v3"), str(CHARTED), str(HERE)]
    sys.addaudithook(deny_backing)
    import combined_successor_raw_entry as combined
    import empty_bootstrap as boot
    import exact_named_raw as raw
    import integrated_original_batch as chart
    import integrated_original_entry as integrated
    from legacy_first_map_acceleration import checked_artifacts

    book, _, producer_cutoff = chart.load_build(BUILD, BUILD_PIN)
    _, specification, _, publication, _ = boot.load_runtime()
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from prospective_0316_solver import denied
    from sparse8_cfo_epoch import RECIPE
    from unified_short_bootstrap import Handoff

    authority = chart.document(stage / "authority.json", authority_pin)
    session = authority["session_id"]
    recording = Path(authority["recording"])
    archive, offer = stage / "tle", stage / "offer.json"
    chart.validate_case(authority, SimpleNamespace(recording=recording, region=offer))
    cutoff = authority["causal_cutoff_utc_ns"]
    if chart.archive_digest(archive, cutoff) != authority["archive_sha256"] or producer_cutoff >= cutoff:
        raise ValueError("The earlier TLE roster or dispatch differs from the original request")
    native = chart.document(stage / "native.json", native_pin)
    chart.match_native(authority, native)
    inventory_digest = authority["inventory_sha256"]
    inventory = chart.document(stage / "inventory.json", inventory_digest)
    chart.match_inventory(authority, session, inventory_digest, inventory)
    boot.bind_native(native, session, inventory_digest, RECIPE, expected="sha256:"+native_pin)

    def saved_inventory(_store, path, *, verify_windows=True):
        if Path(path) != recording or verify_windows:
            raise ValueError("The authenticated saved inventory cannot authorize waveform access")
        return session, inventory_digest, inventory

    handoff = Handoff(session, inventory_digest, RECIPE, native)
    acceleration = book["native"]["--legacy-first-map-fast"]
    acceleration = checked_artifacts(Path(acceleration["path"]), acceleration["sha256"])
    index = book["native"]["--portable-orbit-index"]
    options = SimpleNamespace(recording=recording, archive=archive, region=offer, output=stage / mode,
                              archive_sha256=authority["archive_sha256"], history_risk_route=True,
                              portable_orbit_index=Path(index["path"]), portable_orbit_index_sha256=index["sha256"],
                              portable_orbit_producer_sha256=book["portable_producer"]["sha256"].removeprefix("sha256:"),
                              cairo_six_sheets=True, cairo_residual_layout=False)
    audit = dict(cpu_ns=0, elapsed_ns=0, graph_input_digests=[])
    positive = {}
    if verify_only:
        from leo.analysis.localization_v3.tracks import winning_observations
        from sparse8_time_math import graph_rows

        raw.request_from_handoff(options, handoff)
        corrections = correction_rows(native)
        rows, _ = winning_observations(native)
        graph_rows(rows, corrections)
        by_offset_us = Counter(round(shift*1e6, 4) for _, shift, _ in corrections.values())
        print(json.dumps(dict(case=case, native=native_pin, corrections=len(corrections),
                              by_offset_us=dict(sorted(by_offset_us.items())))))
        return
    with (patch.object(FastScanStore, "inventory", saved_inventory),
          patch.object(FastSegmentSource, "windows", denied), patch.object(ShortWindowReader, "windows", denied),
          effective_graph_time(mode, native, audit, native_pin=native_pin),
          integrated.positive_ports(combined.solver_ports, acceleration, positive)):
        terminal, evidence = raw.publish_active(options, publication, specification, handoff)
    if not audit["graph_input_digests"] or len(set(audit["graph_input_digests"])) != 1:
        raise ValueError("The cached publication did not use one consistent Graph input")
    (published_native,) = options.output.glob("fast-scan-automatic-work/*/detections.json")
    chart.checked(published_native, native_pin)
    chart.checked(options.output / "fast-scan-inputs" / f"{session}.json", inventory_digest)
    timing = dict(cpu_s=(process_time_ns()-started[0])*1e-9, elapsed_s=(perf_counter_ns()-started[1])*1e-9)
    provenance = dict(case=case, mode=mode, terminal=terminal, receiver_sha256=RECIPE,
                      native_sha256=native_pin, authority_sha256=authority_pin, build_sha256=BUILD_PIN,
                      protocol_sha256=chart.tagged_bytes(protocol.read_bytes()),
                      correction_source_sha256=chart.tagged_bytes((HERE / "sparse8_cfo_epoch.py").read_bytes()),
                      worker_source_sha256=chart.tagged_bytes(Path(__file__).read_bytes()),
                      survey_reads=0, waveform_reads=0, acquisition_handoffs=handoff.calls,
                      graph_time=audit, timing=timing, evidence=dict(evidence=evidence["evidence"]),
                      witness_sha256=chart.tagged_bytes((options.output / "exact-named-raw-witness.json").read_bytes()))
    chart.write(stage / f"{mode}-receipt.json", provenance)
    print(json.dumps(dict(case=case, mode=mode, decision=terminal["decision"], timing=timing)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("stage", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--admission")
    args = parser.parse_args()
    admission = {}
    if args.admission:
        from hashlib import sha256

        body = (args.stage / "admission.json").read_bytes()
        if sha256(body).hexdigest() != args.admission:
            raise ValueError("Saved challenge admission digest changed")
        admission = json.loads(body)
        if set(admission) != {"case", "authority_pin", "native_pin"}:
            raise ValueError("Unexpected saved challenge admission")
        admission["protocol"] = HERE / "sparse8-cfo-epoch-transfer-protocol.md"
    worker(args.mode, args.stage, verify_only=args.verify_only, **admission)
