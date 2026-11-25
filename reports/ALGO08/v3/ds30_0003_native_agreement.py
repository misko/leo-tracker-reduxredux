"""Meter one read of each authenticated saved detector packet and compare their signed peaks."""

import argparse
import fcntl
import json
import os
from math import sqrt
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import fmean
from time import perf_counter_ns, process_time_ns

from first30_native_agreement import FULL, LANE, RATE, RULE, SPARSE, canonical, compare, tag


NVME = Path("/srv/postgres-nvme")
CASE = NVME/"leo-ds30-evaluation-20261124/cases/DS30-0003"
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
DRIVER = b"/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py"
PAIR = "sha256:ca94b852592e033d1266d64b0a90e0cd30b8b9e7407490b62de858ca2fd6bf6f"
BOOT = "sha256:fd00d871187f5d2bf59ccf068470b4bb631e1ac8b68fe1d3ce9eba52dd422243"
PACKETS = {
    "installed": (5038333, "sha256:c6ecc9a015215f3007caf84d467e749ad104fc5b15259ae6837b26ad902df87d"),
    "successor": (5162022, "sha256:265e0ba7761c8a17ea0fda96c08f08772ef385fbe73fe347ab8c0ba5111067e1"),
}
NATIVE = "publication/fast-scan-automatic-work/algo08-v2-ff72c71f6e7cce3516326232b5a85376/detections.json"


def local(path):
    if path.resolve(strict=True) != path or path.stat().st_dev != NVME.stat().st_dev or not path.is_relative_to(CASE):
        raise ValueError("Expected the exact local DS30-0003 publication")


def metadata(path, expected):
    local(path)
    if path.stat().st_size >= 50_000:
        raise ValueError("Only small signed comparison metadata is allowed")
    body = path.read_bytes()
    if tag(body) != expected:
        raise ValueError(f"Signed comparison metadata changed at {path.name}")
    return json.loads(body)


def read_bytes_from_device():
    for line in Path("/proc/self/io").read_text().splitlines():
        if line.startswith("read_bytes:"):
            return int(line.split()[1])
    raise ValueError("Kernel process read accounting is unavailable")


def clock():
    return perf_counter_ns(), process_time_ns()


def elapsed(start):
    stop = clock()
    return dict(wall_ns=stop[0]-start[0], cpu_ns=stop[1]-start[1])


def metered_read(path, length, expected):
    local(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_size != length:
            raise ValueError("Signed packet does not have its pinned extent")
        before = read_bytes_from_device()
        usage = getrusage(RUSAGE_SELF)
        now = clock()
        body = os.read(descriptor, length)
        timing = elapsed(now)
        io = read_bytes_from_device()-before
        blocks = getrusage(RUSAGE_SELF).ru_inblock-usage.ru_inblock
    finally:
        os.close(descriptor)
    if len(body) != length or tag(body) != expected:
        raise ValueError("Signed packet digest or verified read length differs")
    return json.loads(body), dict(path=str(path), byte_count=length, sha256=expected,
                                  storage_read_bytes=io, input_blocks=blocks, read=timing)


def driver_idle(pid):
    process = Path("/proc")/str(pid)
    argv = (process/"cmdline").read_bytes().split(b"\0")
    if not any(arg == DRIVER and argv[i+1] == b"run" for i, arg in enumerate(argv[:-1])):
        raise ValueError("Expected the current original field controller")
    if (process/"task"/str(pid)/"children").read_text().split():
        raise ValueError("The field controller has an active child")


def native_identity(packet, result):
    source, signs = packet["source"], packet["provenance"]
    authority = result["raw_identity"]
    if (source["sample_rate_hz"] != RATE or source["session_id"] != authority["session_id"]
            or source["input_manifest_sha256"] != authority["inventory_sha256"]
            or source["raw_recording_authority_digest"] != authority["raw_authority_sha256"]
            or source["analysis_manifest_sha256"] != canonical([
                "cancellation", authority["raw_authority_sha256"], signs["detector_sha256"][7:], source["probes"]])):
        raise ValueError("The saved packet does not bind its original signed acquisition")


def comparable(left, right, raw):
    held, audit = raw["held_anchor_route"], raw["receiver_audit"]["native"]
    recipe = held["receiver_recipe"]
    if (left["provenance"]["detector_sha256"] != "sha256:"+FULL
            or right["provenance"]["detector_sha256"] != canonical(recipe)
            or recipe["installed_sha256"] != FULL or recipe["shortened_sha256"] != SPARSE
            or recipe["streams"] != list(LANE) or recipe["rule"] != RULE or audit["rule"] != RULE
            or recipe["aperture_samples"] != [200_000, 80_000]
            or held["native_sha256"] != PACKETS["successor"][1] or held["refinement_calls"]
            or held["selected"] != sum(len(p["candidates"]) for p in right["source"]["probes"])
            or any(left[key] != right[key] for key in ("clock_anchor", "delivery_clocks", "last_sample_counter"))
            or left["provenance"]["excluded_windows"] != right["provenance"]["excluded_windows"]):
        raise ValueError("Original signed clocks, apertures, or admitted opportunities differ")
    return held, audit


def matched_shorts(offsets):
    values = [row for group in offsets.values() for row in group]
    return {metric: dict(n=len(values), mean=fmean(row[i] for row in values) if values else None,
                         rms=sqrt(fmean(row[i]**2 for row in values)) if values else None)
            for i, metric in enumerate(("signed_cfo_hz", "absolute_epoch_coordinate_samples"))}


def read_pair(pid):
    pair = metadata(CASE/"pair.json", PAIR)
    if not (pair["verified_pair"] and pair["chronological"] and pair["generation"] == 1):
        raise ValueError("Require the original paid pair")
    roots = {role: CASE/role/"attempt-000001" for role in PACKETS}
    results = {role: metadata(path/"result.json", pair["attempt_result_sha256"][role])
               for role, path in roots.items()}
    if (results["installed"]["raw_identity"] != results["successor"]["raw_identity"]
            or any(r["algorithm"] != role or r["authority_sha256"] != pair["authority_sha256"]
                   or r["native_sha256"] != PACKETS[role][1] for role, r in results.items())):
        raise ValueError("The two signed packets do not refer to the original paired recording")
    raw = metadata(roots["successor"]/"publication/unified-short-bootstrap.json", BOOT)
    for role, path in roots.items():
        local(path/NATIVE)
        if (path/NATIVE).stat().st_size != PACKETS[role][0]:
            raise ValueError("Archive size differs before either read")

    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        driver_idle(pid)
        start = clock()
        reads = {role: metered_read(path/NATIVE, *PACKETS[role]) for role, path in roots.items()}
        left, right = (reads[role][0] for role in PACKETS)
        for role, (packet, _) in reads.items():
            native_identity(packet, results[role])
        held, audit = comparable(left, right, raw)
        join = clock()
        counts, offsets, frames = compare(left["source"]["probes"], right["source"]["probes"], audit["native_calls"])
        join_clock = elapsed(join)
        paid = elapsed(start)
    return dict(case="DS30-0003", pair_sha256=PAIR, receiver_summary_sha256=BOOT,
                original_attempts=pair["attempt_result_sha256"], process=dict(
                    cpu=sorted(os.sched_getaffinity(0)), nice=os.nice(0), lease=paid, driver_pid=pid),
                reads={role: proof for role, (_, proof) in reads.items()}, total_native_bytes=sum(x[0] for x in PACKETS.values()),
                join_clock=join_clock, committed_counts=counts, matched_short_distribution=matched_shorts(offsets),
                matched_frame_counts=frames, mixed_eof=held["choice"]["route"],
                packet_keys={role: sorted(packet) for role, (packet, _) in reads.items()},
                candidate_keys=sorted({k for packet, _ in reads.values() for row in packet["source"]["probes"]
                                       for factor in row["candidates"] for k in factor}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-pid", type=int, required=True)
    args = parser.parse_args()
    if os.sched_getaffinity(0) != {3} or os.nice(0) != 15:
        raise ValueError("Use the enrolled low-priority CPU3 worker")
    print(json.dumps(read_pair(args.driver_pid), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
