"""Run the qualified two-lane fifth detector at authentic recorded delivery pace."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from threading import local
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants.dual_lane import DualLane
from . import arrival_queue as pace
from .full_v5_check import _sha

CASE = "DS29-0316"
MAIN, HELPER = 18, 19
MODULE = "tools.pipeline_eval.qualification.dual_lane_pace"
MEASURED_PARENT = "97d798202a4dc7096043c9d3210402ee7e0449a37b0ce388589d5a206d543164"
MODE = "candidate"
METHOD = "dual_lane_fifth"
REPORT = pace.PARENT.parents[1] / "latency-and-support/dual-lane"
LIBRARY = "libleo-dual-lane.so"
DETECTOR = "libleo-adaptive-detector.so.1"


def freeze(work, benchmark, report):
    from . import dual_lane_eval as timing

    if work.exists() or (report / "source-lock.json").exists():
        raise FileExistsError("prospective paced dual-lane plan already exists")
    qualified = REPORT / "native-lock.json"
    observed = whole_iq.read(qualified)
    for name, value in observed["files"].items():
        whole_iq.checked(REPORT / name, value)
    measurement = pace.readgz(REPORT / "native-measurements.json.gz")
    expected = len(timing.CORES) * len(timing.SEGMENTS) * timing.WINDOWS
    if len(measurement["parity"]) != 2 * expected or not all(
        r["exact_rows_and_regions"] for r in measurement["controls"]
    ):
        raise ValueError("paced candidate did not complete measured dual-lane parity")
    reference = whole_iq.read(whole_iq.checked(pace.REPORT / "stage-lock.json", MEASURED_PARENT))
    original = whole_iq.read(
        whole_iq.checked(pace.REPORT / "source-lock.json", reference["files"]["source-lock.json"])
    )
    received = original["cases"][CASE]
    chosen = received["modes"][MODE]
    work.mkdir(parents=True)
    report.mkdir(parents=True, exist_ok=True)
    name = chosen["events"]
    write(report / name, whole_iq.checked(pace.REPORT / name, chosen["sha256"]).read_bytes())
    build = whole_iq.read(REPORT / "native-build.json")
    assets = {}
    for leaf, sha in build["files"].items():
        source = whole_iq.checked(benchmark / "build" / leaf, sha)
        target = work / leaf
        write(target, source.read_bytes())
        target.chmod(0o644)
        assets[leaf] = dict(path=str(target), sha256=sha)
    src = report / "source-lock.json"
    files = (Path(__file__), Path(__file__).parents[1] / "variants/dual_lane.py")
    save_json(
        src,
        dict(
            original,
            cases={CASE: dict(received, cpu=MAIN, modes={MODE: chosen})},
            assets=assets,
            programs=original["programs"] | {str(f): _sha(f) for f in files},
            one_slot_stage_sha256=MEASURED_PARENT,
            native_measurement_lock_sha256=_sha(qualified),
            cpus=[MAIN, HELPER],
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
        ),
    )
    save_json(work / "launch-lock.json", {"source_lock_sha256": _sha(src)})


@contextmanager
def raw_configuration():
    counters = local()
    prior = pace.native_visit

    def detector(capture, mode, assets, stack):
        if mode != MODE:
            raise ValueError("the one-case paced study declared unconditional fifth center")
        item = assets[LIBRARY]
        path = whole_iq.checked(Path(item["path"]), item["sha256"])
        whole_iq.checked(Path(assets[DETECTOR]["path"]), assets[DETECTOR]["sha256"])
        port = stack.enter_context(DualLane(path, capture["edge"], helper_cpu=HELPER))

        def analyze(samples):
            output, profile = port.analyze(samples, trace=True)
            lane0, lane1 = profile["lanes"]
            if (lane0["cpu"], lane1["cpu"]) != (MAIN, HELPER):
                raise ValueError("unbound lane used the recorded arrival replay")
            counters.helper = lane1["cpu_ns"]
            return output

        return analyze

    def visit(frame, analyze, detect, policy):
        counters.helper = 0
        envelope, (wall, caller) = prior(frame, analyze, detect, policy)
        return envelope, (wall, caller + counters.helper)

    with patch.multiple(
        pace,
        CPUS={CASE: MAIN},
        MODES=(MODE,),
        MODULE=MODULE,
        build_native=detector,
        native_visit=visit,
    ):
        yield


def run(work, report):
    with raw_configuration():
        pace.replay(work, report)


def publish(work, report):
    from . import arrival_queue_cost as cost
    from . import arrival_queue_position as position
    from . import arrival_queue_results as results

    with raw_configuration():
        binding = pace.plan(work, report)
        spec = binding["cases"][CASE]["modes"][MODE]
        events = pace.readgz(whole_iq.checked(report / spec["events"], spec["sha256"]))
        attempt = work / CASE / MODE
        if (attempt / "visits.jsonl").is_file():
            trace, witness, service, complete = results.terminal(attempt, events)
        else:
            trace, witness, complete = [], None, False
            service = whole_iq.read(attempt / "service.json")
            whole_iq.checked(attempt / "service.log", service["log_sha256"])
        row = results.observed(trace, witness, CASE, MODE, complete, events)
        pace.writegz(report / "paced-events.json.gz", trace)
        save_json(report / "paced-summary.json", row)
        save_json(report / "witness.json", dict(worker=witness, service=service))
        write(report / "service.log", (attempt / "service.log").read_bytes())
        files = (
            "source-lock.json",
            "paced-events.json.gz",
            "paced-summary.json",
            "witness.json",
            "service.log",
            spec["events"],
        )
        save_json(
            report / "paced-lock.json",
            dict(cases=[CASE], files={n: _sha(report / n) for n in files}),
        )
        if complete:
            with (
                patch.object(position, "METHODS", {MODE: METHOD}),
                patch.object(cost, "CPUS", {CASE: MAIN}),
            ):
                position.run(work, report, MODE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "replay", "worker", "publish"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--benchmark", type=local_output)
    parser.add_argument("--out", type=local_output, default=REPORT / "paced")
    args = parser.parse_args()
    if args.action == "worker":
        with raw_configuration():
            pace.execute(args.work)
    elif args.action == "freeze":
        freeze(args.work, args.benchmark, args.out)
    else:
        {"replay": run, "publish": publish}[args.action](args.work, args.out)
