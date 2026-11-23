"""Calibrate a single durable detection seal and separate it from reader throughput."""

import argparse
from collections import defaultdict
from contextlib import contextmanager
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from acquisition_throughput import gates, minimum_rate

from .full_short_cold import MEASURED, freeze
from .full_short_score import INVENTORY_SHA, PRIOR_SHORT_RECEIPT_SHA, SCENARIOS
from .scout_readout_trial import check_machine
from .sparse_cold_input import ARCHIVE, ARCHIVED_DETECTION_SHA, RUNTIME, io_snapshot, verified


PREFIX_SHA = "c20d38fbb6ba67e187445bb8300f32b8d1e514f899067aadab7d0e7fe37cef6a"
ARENA_RECEIPT_SHA = "80ec5eeeb16be5f262e28247dd9ffa50078e3d05b57b5e57e705512d7a75dda2"
ORDERS = (("prefix", "full"), ("full", "prefix"))
SOURCE_FIELDS = ("session_id", "input_manifest_sha256", "raw_recording_authority_digest", "analysis_manifest_sha256")


@contextmanager
def clock(rows, name):
    cpu, wall = process_time_ns(), perf_counter_ns()
    try:
        yield
    finally:
        rows[name].append(dict(cpu_ns=process_time_ns()-cpu, wall_ns=perf_counter_ns()-wall))


def measure(doc, expected_sha, output):
    from leo.contracts.digests import canonical_digest
    from leo.storage import fast_scan

    # Observe the production publication primitives without replacing their operations.
    clocks = defaultdict(list)
    serialize, fsync = fast_scan.canonical_json_bytes, os.fsync
    expected_source = {key: doc["source"][key] for key in SOURCE_FIELDS}
    expected_provenance = doc["provenance"]
    io_before, before = io_snapshot(), resource.getrusage(resource.RUSAGE_SELF)

    def observe_serialize(document):
        with clock(clocks, "canonical_json"):
            return serialize(document)

    def observe_fsync(fd):
        name = "directory_fsync" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file_fsync"
        with clock(clocks, name):
            return fsync(fd)

    with (patch.object(fast_scan, "canonical_json_bytes", observe_serialize),
          patch.object(os, "fsync", observe_fsync), clock(clocks, "complete")):
        with clock(clocks, "immutable_write"):
            fast_scan.immutable_json(output, doc)
        with clock(clocks, "readback"):
            content = output.read_bytes()
        with clock(clocks, "parse"):
            loaded = json.loads(content)
        with clock(clocks, "source_verification"):
            source, provenance = loaded["source"], loaded["provenance"]
            detector = provenance["detector_sha256"].removeprefix("sha256:")
            binding = canonical_digest(["cancellation", source["raw_recording_authority_digest"], detector, source["probes"]])
            if (sha256(content).hexdigest() != expected_sha
                    or binding != source["analysis_manifest_sha256"] or provenance != expected_provenance
                    or any(source[key] != value for key, value in expected_source.items())
                    or len(loaded["delivery_clocks"]) != provenance["window_count"]
                    or len(source["probes"]) != 2 * provenance["processed_windows"]):
                raise ValueError("The durable readback differs from its signed source or detector binding")
    after, io_after = resource.getrusage(resource.RUSAGE_SELF), io_snapshot()
    stages = {}
    for key, times in clocks.items():
        only, = times
        stages[key] = only
    return dict(bytes_written=len(content), sha256=expected_sha, source=expected_source, stages=stages,
                process_io_delta={key: value-io_before[key] for key, value in io_after.items()},
                resource_input_blocks=after.ru_inblock-before.ru_inblock, resource_output_blocks=after.ru_oublock-before.ru_oublock)


def calibration(parent, prefix, output):
    from leo.storage import fast_scan

    machine = check_machine()
    parent = parent.resolve(strict=True)
    if Path("/srv/bulk/leo-dev") not in (parent, *parent.parents):
        raise ValueError("Durability calibration requires the existing private XFS staging root")
    filesystem = subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip()
    if filesystem != "xfs":
        raise ValueError("Expected XFS")
    verified(Path(fast_scan.__file__), RUNTIME["leo.storage.fast_scan"])
    full, = (ARCHIVE / "fast-scan-automatic-work").glob("*/detections.json")
    sources = {"prefix": (prefix, PREFIX_SHA, 140853), "full": (full, ARCHIVED_DETECTION_SHA, 5590695)}
    preload = defaultdict(list)
    docs = {}
    with clock(preload, "load_and_verify_source"):
        for name, (path, digest, size) in sources.items():
            content = verified(path, digest)
            if len(content) != size:
                raise ValueError("Unexpected saved detection document size")
            docs[name] = json.loads(content)
        if docs["prefix"]["source"]["input_manifest_sha256"] != docs["full"]["source"]["input_manifest_sha256"]:
            raise ValueError("The two saved documents refer to different raw inventories")
    pairs = []
    with TemporaryDirectory(dir=parent, prefix="leo-private-seal-scaling-") as temp:
        private = Path(temp)
        for pair, order in enumerate(ORDERS):
            pairs.append([dict(arm=name, **measure(docs[name], sources[name][1], private / f"{pair}-{name}.json"))
                          for name in order])
    freeze(output, dict(machine=machine, filesystem=filesystem, orders=ORDERS, pairs=pairs, saved_source_load=preload,
                        input_paths={name: str(source[0]) for name, source in sources.items()}))


def seal_clocks(receipt):
    wall_ns = receipt["wall_ns"]-receipt["acquire_wall_ns"]
    cpu_ns = receipt["cpu_ns"]-receipt["acquire_cpu_ns"]
    return dict(wall_ns=wall_ns, cpu_ns=cpu_ns)


def shared_tails(calibration_rows, prefix_rows):
    full = [row["stages"]["complete"] for row in calibration_rows if row["arm"] == "full"]
    waits = [row["stages"]["complete"] for row in calibration_rows] + [seal_clocks(row) for row in prefix_rows]
    longest_wait = max(0, *(row["wall_ns"]-row["cpu_ns"] for row in waits))
    return dict(optimistic=min(row["wall_ns"] for row in full) / 1e9,
                stressed=(max(row["cpu_ns"] for row in full) + longest_wait) / 1e9,
                maximum_observed_non_cpu_seal_s=longest_wait / 1e9)


def transfer(inventory, rate_measured, reader_rate, overhead, tails, fraction):
    baseline = gates(inventory, rate_measured, fraction)
    corrected = {}
    for key in ("optimistic", "stressed"):
        charge = tails[key]
        corrected[key] = dict(
            once_sealed=gates(inventory, reader_rate, fraction, startup_s=charge),
            once_sealed_with_worker=gates(inventory, reader_rate, fraction, startup_s=charge+overhead),
            required_reader_MB_s=[minimum_rate(inventory, fraction, gate, startup_s=charge) for gate in (0, 1)],
            required_reader_with_worker_MB_s=[minimum_rate(inventory, fraction, gate, startup_s=charge+overhead) for gate in (0, 1)],
        )
    return dict(old_through_seal_scaled_per_MB=baseline,
                old_through_seal_with_worker=gates(inventory, rate_measured, fraction, startup_s=overhead),
                **corrected)


def score(calibration_path, output):
    calibration = json.loads(calibration_path.read_bytes())
    if calibration["orders"] != [list(order) for order in ORDERS]:
        raise ValueError("Expected two reversed calibrations")
    receipts = {"receiver": ("full-short-cold", PRIOR_SHORT_RECEIPT_SHA), "arena": ("full-short-arena", ARENA_RECEIPT_SHA)}
    acquisitions = {label: json.loads(gzip.decompress(verified(MEASURED / (name+".json.gz"), pin)))["acquisition"]
                    for label, (name, pin) in receipts.items()}
    prefix_rows = [row for acquisition in acquisitions.values() for pair in acquisition["repeats"] for row in pair]
    calibration_rows = [row for pair in calibration["pairs"] for row in pair]
    tails = shared_tails(calibration_rows, prefix_rows)
    inventory = json.loads(verified(MEASURED / "acquisition-throughput.json", INVENTORY_SHA))["rows"]
    if len(inventory) != 55 or sum(not row["stages"][0] for row in inventory) != 3:
        raise ValueError("Historical inventory or uninstrumented failures changed")
    groups = {"all": inventory, "cold": [r for r in inventory if r["initial_residency"] is not None and r["initial_residency"] < .2],
              "warm": [r for r in inventory if (r["initial_residency"] or 0) > .95]}
    outcomes = {}
    for label, acquisition in acquisitions.items():
        results = []
        for pair, rows in enumerate(acquisition["repeats"]):
            for row in rows:
                measured = row["effective_compressed_MB_per_s"]
                reader = acquisition["compressed_bytes"]*1000/row["acquire_wall_ns"]
                overhead = row["omitted_subprocess_wall_ns"]/1e9
                measurements = dict(reader_MB_s=reader, through_seal_MB_s=measured,
                                    reader_wall_ns=row["acquire_wall_ns"], reader_cpu_ns=row["acquire_cpu_ns"],
                                    seal=seal_clocks(row), worker_overhead_s=overhead)
                projections = {group: {scenario: transfer(selected, measured, reader, overhead, tails, fraction)
                               for scenario, fraction in SCENARIOS.items()} for group, selected in groups.items()}
                results.append(dict(pair=pair, arm=row["arm"], measurements=measurements, projections=projections))
        outcomes[label] = results
    freeze(output, dict(receipts=receipts, calibration=calibration, calibration_sha256=sha256(calibration_path.read_bytes()).hexdigest(),
                        inventory_sha256=INVENTORY_SHA, shared_once_per_recording_tails_s=tails,
                        uninstrumented_failures_unchanged=3, projections=outcomes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_subparsers(dest="action", required=True)
    calibration_cli = action.add_parser("calibrate")
    for name in ("parent", "prefix", "output"):
        calibration_cli.add_argument(name, type=Path)
    score_cli = action.add_parser("score")
    for name in ("calibration_path", "output"):
        score_cli.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"calibrate": calibration, "score": score}[args.pop("action")](**args)
