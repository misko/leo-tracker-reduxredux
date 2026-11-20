"""Replay the post-GLRT deadline policy with cancellable, single-core numerical workers."""

import argparse
import os
from functools import partial
from importlib.util import find_spec
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import implementation_digest, local_output, module_name, run_one, save_json
from ..variants import deadline_receiver, lean_receiver_cli_benchmark
from .full_receiver_comparison import read, sha
from .native_agreement_cascade_fresh import cpu_time

REPORT = corpus.REPO / "reports/2026_11_19_receiver_screening/deployment/deadline-live"
CASES = {
    "short": ["DS26-0036", 30, 15],
    "long": ["DS26-0036", 180, 16],
    "failure": ["DS26-0191", 180, 13],
}
METHODS = ("v5_secant_fit", "portable_native_clock")


def sources():
    return {
        **{
            method: implementation_digest(method, Path(find_spec(module_name(method)).origin))
            for method in METHODS
        },
        "controller": sha(Path(deadline_receiver.__file__)),
        "runner": sha(Path(__file__)),
        "protocol": sha(REPORT / "PROTOCOL.md"),
    }


def plan():
    return {"cases": CASES, "reserve_s": deadline_receiver.RESERVE_S, "source": sources()}


def classify(row):
    result = row["result"]
    # The legacy process wrapper uses "unavailable" for exceptions after inference started.
    reason = result.get("reason") or ""
    scientific_exception = reason.startswith(("ValueError:", "AssertionError", "ArithmeticError:"))
    if (
        result["status"] == "unavailable"
        and scientific_exception
        and result["metrics"].get("candidate_s", 0) > 0
    ):
        return dict(result, status="failed")
    return result


def trial(key, work, output):
    ident, seconds, cpu = CASES[key]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10:
        raise ValueError("use the prespecified core at low scheduling priority")
    if read(output / "plan.json") != plan():
        raise ValueError("deadline receiver implementations changed after sealing")
    work.mkdir(parents=True, exist_ok=False)
    ids, digests = corpus._selection("ds26-all159")
    if ident not in ids:
        raise ValueError("case outside frozen roster")
    item = corpus._index(corpus._read_frozen("inputs.jsonl", digests))[ident]
    started = perf_counter()
    compact, _ = next(corpus.cases("ds26-all159", work / "cache", {ident}))
    native = lean_receiver_cli_benchmark.project(item, corpus.DEFAULT_BULK)
    if (
        not compact["request_path"]
        or native.get("unsupported")
        or native["offer"] != compact["regions"][0]
        or native["expected"]["native"] != compact["native_sha256"].removeprefix("sha256:")
        or native["expected"]["catalogue"] != sha(Path(compact["catalog_path"]))
    ):
        raise ValueError("the two workers require identical complete native inputs and tile")
    request = read(Path(compact["request_path"]))
    latest = max(
        (int(name.split("-")[0]), checksum.removeprefix("sha256:"))
        for name, checksum in request["causal_snapshots"].items()
        if int(name.split("-")[0]) < item["cutoff_utc_ns"]
    )
    if (
        request["job"]["evaluation_reference"] is not None
        or request["job"]["native_input"]["sha256"] != compact["native_sha256"]
        or request["job"]["search_center"] != native["offer"]["center"]
        or latest != (item["catalog_timestamp_ns"], native["expected"]["catalogue"])
    ):
        raise ValueError("invalid compact inference request")
    prep = perf_counter() - started
    measurements = {}

    def worker(name, case, limit):
        tick = cpu_time()
        row = run_one(name, case, work, limit, cpu)
        measurements[name] = dict(row, measured_cpu_s=cpu_time() - tick)
        return classify(row) if name == METHODS[0] else row["result"]

    routed = deadline_receiver.route(
        partial(worker, METHODS[0], compact),
        partial(worker, METHODS[1], native),
        total_s=seconds,
    )
    save_json(
        output / f"{key}.json",
        dict(
            id=ident,
            key=key,
            cpu=cpu,
            total_s=seconds,
            prepare_wall_s=prep,
            tile=native["offer"],
            native_sha256=item["native"]["sha256"],
            catalog_sha256=item["catalog"]["sha256"],
            track_config_sha256=item["track_config"]["sha256"],
            input_sha256=sha(Path(compact["request_path"])),
            plan_sha256=sha(output / "plan.json"),
            measurements=measurements,
            **routed,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", *CASES))
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    out = local_output(args.out)
    if args.action == "seal":
        save_json(out / "plan.json", plan())
    else:
        if args.work is None:
            parser.error("--work is required for a live replay")
        trial(args.action, local_output(args.work), out)


if __name__ == "__main__":
    main()
