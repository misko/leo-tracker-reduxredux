"""Pass one sealed three-of-four strongest packet through the frozen field solver."""

import argparse
from functools import partial
from hashlib import sha256
import os
from pathlib import Path
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


CASE = "DS30-0086"
STAGE = Path("/dev/shm/leo-v3-cfo-epoch-0086-saved01")
BOUND = "602a2075d0acf1c0504fca56cb3941a03f7dfa20eb2dfce9edcc79f488f5a248"
CHARTED = Path("/tmp/leo-v3-integrated-original-batch")
BUILD = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/frozen-build/build.json")
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"


def validate_receipts(inputs, authority, archived, candidate, recipe, member_plan):
    from three_quarter_members import HELD, checked, digest, read

    audit = read(inputs / "audit.json")
    protocol = HERE / "three-quarter-members-protocol.md"
    expected = next(row for row in audit["records"] if row["case"] == CASE)
    proof = read(inputs / "index-proof.json")
    if (sha256(checked(protocol)).hexdigest() != audit["protocol_sha256"]
            or max(audit["gates"]["stage_scaled_factor_linear_s"].values()) > .5
            or expected["model"]["stage_scaled_factor_linear_s"] > expected["installed_s"] / 2
            or digest(archived) != expected["historical_final_native_sha256"]
            or archived["provenance"]["detector_sha256"] != HELD
            or not expected["matched_original_counterfactual"]
            or digest(candidate) != expected["proposed_native_sha256"]
            or digest(recipe) != expected["receiver_recipe_sha256"]
            or digest(member_plan) != expected["members_sha256"]
            or {case: row["issued"] for case, row in proof.items()} != {"DS30-0016": 808, "DS30-0049": 384}
            or not proof["DS30-0016"]["complete_raw_authority"]):
        raise ValueError("Frozen input, physical counter proof or timing advance criterion is not satisfied")
    omit = {i for row in member_plan if row["omit"] for i in range(row["first_visit"], row["stop_visit"])}
    sample = candidate["provenance"]["research_sampling"]
    if (sample["skipped_acquisition_windows"] != sorted(omit) or sample["original_packet_sha256"] != expected["parent_native_sha256"]
            or sample["members_sha256"] != expected["members_sha256"] or sample["original_inventory_sha256"] != authority["inventory_sha256"]
            or candidate["source"]["probes"] != [row for row in archived["source"]["probes"] if row["visit_index"] not in omit]
            or archived["delivery_clocks"] != candidate["delivery_clocks"]):
        raise ValueError("The requested skip-acquisition census or exact retained factor sequence changed")
    return expected


def worker(inputs, output, *, probe=False):
    started = process_time(), perf_counter()
    sys.path[:0] = [str(CHARTED / "reports/ALGO08/v3"), str(CHARTED)]
    from sparse8_cfo_epoch_saved import deny_backing
    sys.addaudithook(deny_backing)
    import combined_successor_raw_entry as combined
    import empty_bootstrap as boot
    import exact_named_raw as raw
    import integrated_original_batch as chart
    import integrated_original_entry as integrated
    from legacy_first_map_acceleration import checked_artifacts
    from visit_frame_raw_0016 import resident

    book, _, producer_cutoff = chart.load_build(BUILD, BUILD_PIN)
    _, specification, _, publication, source_clocks = boot.load_runtime()
    from tools import algo08_position, algo08_scan
    if (Path(algo08_scan.__file__).resolve() != boot.PAYLOAD / boot.SCANNER
            or Path(algo08_position.__file__).resolve() != boot.PAYLOAD / "tools/algo08_position.py"):
        raise ValueError("The saved solver and scanner must resolve to the frozen installed package")
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from prospective_0316_solver import denied
    from unified_short_bootstrap import Handoff
    with patch.object(sys, "path", list(sys.path)):
        from three_quarter_members import checked, digest, read, report_adapter, write

    authority = read(STAGE / "authority.json", BOUND)
    inventory = read(STAGE / "inventory.json", authority["inventory_sha256"])
    prior = read(STAGE / "native.json")
    native, recipe, members = (read(inputs / f"{CASE}-{name}.json") for name in ("native", "recipe", "members"))
    source = validate_receipts(inputs, authority, prior, native, recipe, members)
    session, inventory_digest = authority["session_id"], authority["inventory_sha256"]
    recording, archive, offer = Path(authority["recording"]), STAGE / "tle", STAGE / "offer.json"
    chart.validate_case(authority, SimpleNamespace(recording=recording, region=offer))
    chart.match_inventory(authority, session, inventory_digest, inventory)
    chart.match_native(authority, native)
    detector = digest(recipe)[7:]
    boot.bind_native(native, session, inventory_digest, detector, expected=source["proposed_native_sha256"])
    cutoff = authority["causal_cutoff_utc_ns"]
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if not refs or producer_cutoff >= cutoff or chart.archive_digest(archive, cutoff) != authority["archive_sha256"]:
        raise ValueError("Require the already resident original causal archive and earlier portfolio index")
    cache = resident([str(ref.path) for ref in refs])
    handoff = Handoff(session, inventory_digest, detector, native)

    def saved_inventory(_store, path, *, verify_windows=True):
        if Path(path) != recording or verify_windows:
            raise ValueError("Only the original detached signed inventory may authorize the saved handoff")
        return session, inventory_digest, inventory

    acceleration_file = book["native"]["--legacy-first-map-fast"]
    acceleration = checked_artifacts(Path(acceleration_file["path"]), acceleration_file["sha256"])
    index = book["native"]["--portable-orbit-index"]
    options = SimpleNamespace(recording=recording, archive=archive, region=offer, output=output / "candidate",
                              archive_sha256=authority["archive_sha256"], history_risk_route=True,
                              portable_orbit_index=Path(index["path"]), portable_orbit_index_sha256=index["sha256"],
                              portable_orbit_producer_sha256=book["portable_producer"]["sha256"].removeprefix("sha256:"),
                              cairo_six_sheets=True, cairo_residual_layout=False)
    raw.request_from_handoff(options, handoff)
    if probe:
        print(f"Ready {CASE} with {source['physical']['retained_admitted']} retained original visits")
        return
    if os.sched_getaffinity(0) != {2} or os.nice(0) < 15:
        raise ValueError("Require a naturally acquired shared low-priority CPU2 lease")
    output.mkdir(mode=0o700)
    write(output / "admission.json", dict(case=CASE, build_sha256=BUILD_PIN, scope=source,
          authority=authority, residence=cache, archive_clocks=source_clocks,
          worker_sha256=sha256(checked(Path(__file__))).hexdigest(), inputs={file: sha256(checked(inputs / file)).hexdigest()
          for file in ("audit.json", "index-proof.json", f"{CASE}-native.json", f"{CASE}-members.json", f"{CASE}-recipe.json")}))
    positive = {}
    with (patch.object(FastScanStore, "inventory", saved_inventory),
          patch.object(FastSegmentSource, "windows", denied), patch.object(ShortWindowReader, "windows", denied),
          patch.object(algo08_scan, "scan_report", partial(report_adapter, algo08_scan.scan_report)),
          integrated.positive_ports(combined.solver_ports, acceleration, positive)):
        terminal, witness = raw.publish_active(options, publication, specification, handoff)
    saved_native, = options.output.glob("fast-scan-automatic-work/*/detections.json")
    checked(saved_native, source["proposed_native_sha256"])
    checked(options.output / "fast-scan-inputs" / f"{session}.json", inventory_digest)
    if (terminal["counts"].get("skipped_acquisition") != source["physical"]["omitted_visits"] or handoff.calls != 1
            or resident([str(ref.path) for ref in refs]) != cache):
        raise ValueError("The saved handoff lost original custody, indexing or its skipped-acquisition census")
    timing = dict(cpu_s=process_time()-started[0], elapsed_s=perf_counter()-started[1])
    write(output / "worker.json", dict(terminal=terminal, timing=timing, analysis=witness["timing"], ports=positive,
          waveform_reads=0, survey_reads=0, result_evidence=witness["evidence"], handoffs=handoff.calls))
    from clean_saved_0169_trial import output_seal

    write(output / "prediction-seal.json", output_seal(output))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("inputs", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--probe", action="store_true")
    args = cli.parse_args()
    worker(args.inputs, args.output, probe=args.probe)
