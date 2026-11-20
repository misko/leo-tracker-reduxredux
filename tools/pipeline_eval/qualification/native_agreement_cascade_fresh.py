"""Measure one native-start cascade worker on an authenticated roof recording."""

import argparse
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter, process_time

from .. import corpus
from ..__main__ import encoded, local_output, run_one, save_json
from ..variants import lean_receiver_cli as clock
from ..variants import lean_receiver_cli_benchmark as native
from ..variants import native_agreement_cascade as cascade


def cpu_time():
    child = getrusage(RUSAGE_CHILDREN)
    return process_time() + child.ru_utime + child.ru_stime


def compact_only(item, projected, work, cpu, timeout):
    """Bind compact only when the trusted original tile needs its fallback."""
    before = cpu_time(), perf_counter()
    issues = {}
    path = corpus._request(
        item, corpus.DEFAULT_BULK, work, Path(projected["files"]["native"]), issues
    )
    if path is None:
        raise ValueError(f"missing trusted compact request: {issues}")
    case = dict(
        id=item["id"],
        panel=item["panel"],
        regions=item["regions"],
        native_path=projected["files"]["native"],
        request_path=str(path),
        session_id=item["session_id"],
        native_sha256="sha256:" + item["native"]["sha256"],
    )
    row = run_one("v5_secant_fit", case, work, timeout, cpu)
    return dict(
        row, measured_cpu_s=cpu_time() - before[0], wall_from_native_s=perf_counter() - before[1]
    )


def trial(ident, cpu, work, timeout, *, control=False):
    if set(os.sched_getaffinity(0)) != {cpu}:
        raise ValueError("pin this command to its single measurement CPU")
    from .anchor_receiver_full import attempt, sources
    from .full_v5_check import _load_case
    from .native_joint_trial import BUNDLE
    from .native_lean_eval import request

    work.mkdir(parents=True, exist_ok=False)
    item = _load_case(ident)
    started = cpu_time(), perf_counter()
    projected = native.project(item, corpus.DEFAULT_BULK)
    if "unsupported" in projected:
        raise ValueError(projected["unsupported"])
    packet, paths = request(item, "native")
    request_sha = corpus._sha(encoded(packet))
    query = dict(id=ident, recording=ident, cohort="fresh", packet=packet)

    def smooth():
        row = clock.solve(
            **{k: v for k, v in projected.items() if k != "id"}, solver="smooth-clock"
        )
        if row["input_sha256"] != request_sha:
            raise ValueError("standalone smooth-clock scientific request differs")
        return row

    def anchors():
        row = attempt(query, paths, cpu, BUNDLE)
        if row["input_sha256"] != request_sha:
            raise ValueError("curve anchor scientific request differs")
        return row

    source = sources(BUNDLE)
    outcome = cascade.execute(
        smooth, anchors, lambda: compact_only(item, projected, work, cpu, timeout)
    )
    # Bubblewrap's separate PID namespace leaves its worker CPU outside RUSAGE_CHILDREN.
    native_cpu = sum(
        outcome[key].get("worker", {}).get("cpu_s", 0) for key in ("smooth", "anchors")
    )
    waited_cpu = cpu_time() - started[0]
    row = dict(
        outcome,
        id=ident,
        method=cascade.METHOD,
        cpu=cpu,
        request_sha256=request_sha,
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        tile=packet["offer"],
        anchor_sources=source,
        supervisor_and_waited_cpu_s=waited_cpu,
        sandbox_native_cpu_s=native_cpu,
        accounted_cpu_s=waited_cpu + native_cpu,
        wall_from_native_s=perf_counter() - started[1],
    )
    if sources(BUNDLE) != source:
        raise ValueError("anchor sources changed during execution")
    save_json(work / "cascade.json", row)
    print(
        ident,
        row["route"],
        row["result"]["status"],
        round(row["wall_from_native_s"], 3),
        flush=True,
    )
    if control:
        baseline = compact_only(item, projected, work, cpu, timeout)
        save_json(work / "compact-only.json", baseline)
        print(
            ident,
            "compact-only",
            baseline["result"]["status"],
            round(baseline["wall_from_native_s"], 3),
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=480)
    parser.add_argument("--control", action="store_true")
    args = parser.parse_args()
    trial(args.id, args.cpu, local_output(args.work), args.timeout, control=args.control)


if __name__ == "__main__":
    main()
