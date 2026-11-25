"""Time a balanced matched comparison of two fully verified owned-window decoders."""

import argparse
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import median
import subprocess
import sys
from time import perf_counter_ns, process_time_ns

from .zstd_literal_pair import Decoder, HERE, digest
from .zstd_literal_pair_check import CASES, FILES, load_owned, qualified_reader, restrict_payloads


LEASE = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
ORDERS = (("stock", "paired"), ("paired", "stock")) * 3


def run_arm(case, runtime, arm):
    FusedMember, stock, paired, hasher = runtime
    library = stock if arm == "stock" else paired
    first = getrusage(RUSAGE_SELF)
    start, cpu = perf_counter_ns(), process_time_ns()
    reader, chunk, authority = qualified_reader(case)
    opened = perf_counter_ns()
    with closing(FusedMember(reader, chunk, library, hasher, build_maps=False, owned_windows=True)) as member:
        proof = [(item.index.sequence, item.index.iq_sha256) for item in member.windows()]
        if not member.eof or len(proof) != chunk.window_count:
            raise ValueError("The actual verified-once iterator did not reach original EOF")
        audit = member.audit()
    elapsed, cpu = perf_counter_ns()-start, process_time_ns()-cpu
    final = getrusage(RUSAGE_SELF)
    clocks = dict(wall_ns=elapsed, cpu_ns=cpu, manifest_admission_wall_ns=opened-start,
                  input_blocks=final.ru_inblock-first.ru_inblock,
                  minor_faults=final.ru_minflt-first.ru_minflt, major_faults=final.ru_majflt-first.ru_majflt,
                  process_max_rss_kib=final.ru_maxrss, reader=audit)
    counts = dict(paired.finished) if arm == "paired" and paired.finished is not None else None
    return (authority, proof), dict(arm=arm, clocks=clocks, counts=counts)


def compare(case, runtime):
    _, _, counts = CASES[case]
    repetitions = []
    reference = None
    for ordering in ORDERS:
        pair = []
        for arm in ordering:
            proof, result = run_arm(case, runtime, arm)
            if reference is None:
                reference = proof
            if proof != reference:
                raise ValueError("Original ordered verified windows differ")
            if arm == "paired":
                work = result["counts"]
                if (work is None or work["route"] != "paired" or
                    tuple(work[key] for key in ("pair_count", "singletons", "mixed_blocks")) != counts):
                    raise ValueError("Clause activation differs from the sealed parity control")
            pair.append(result)
        repetitions.append(pair)
    by_order = {}
    groups = {"both": repetitions, "stock_first": repetitions[::2], "paired_first": repetitions[1::2]}
    for bucket, rows in groups.items():
        deltas = {}
        for key in ("wall_ns", "cpu_ns"):
            values = [{entry["arm"]: entry["clocks"][key] for entry in pair} for pair in rows]
            old = sum(value["stock"] for value in values)
            new = sum(value["paired"] for value in values)
            deltas[key] = dict(median_paired_gain=median(value["stock"] - value["paired"] for value in values),
                               stock_total=old, paired_total=new, total_speedup=old / new)
        by_order[bucket] = deltas
    return dict(case=case, authority=reference[0], retained_window_hashes=reference[1], runs=repetitions,
                summary=by_order, source_cold=False, source_storage="existing full-resident detached tmpfs")


def run(paired_lib, pin, history, hasher, case):
    if (case not in CASES or os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15 or
        subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip() != "idle"):
        raise ValueError("Use one fresh CPU2 nice-15 idle-I/O slot for the fixed detached original")
    restrict_payloads(tuple(CASES[case][0] / name for name in FILES))
    from .zstd_literal_pair_clock_capsule import isolation

    proof = isolation(case)
    runtime = load_owned(Decoder(paired_lib, pin), history, hasher)
    if not os.path.samestat(os.fstat(sys.stdin.fileno()), LEASE.stat()):
        raise ValueError("Inherit the nonblocking shared Gauss lease as stdin")
    fcntl.flock(sys.stdin.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    result = compare(case, runtime)
    print(json.dumps(dict(cases=[result], candidate_pin=pin, filesystem_isolation=proof,
                          native_source_sha256=digest((HERE / "zstd_literal_pair.c").read_bytes()),
                          comparator_sha256=digest(Path(__file__).read_bytes()),
                          scope="fresh strict member open/hash, complete owned-window decode and signed verification through EOF/close",
                          startup_outside_arm_clocks="imports and pinned native library loading",
                          raw_adc_and_publication_not_run=True), sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_library", type=Path)
    parser.add_argument("candidate_sha256")
    parser.add_argument("ordinary_history", type=Path)
    parser.add_argument("signed_hasher", type=Path)
    parser.add_argument("case", choices=CASES)
    args = parser.parse_args()
    run(args.candidate_library, args.candidate_sha256, args.ordinary_history, args.signed_hasher, args.case)
