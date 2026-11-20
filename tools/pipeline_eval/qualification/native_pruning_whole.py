"""Recorded-pace, four-region whole-IQ qualification for exact grid publication."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from threading import local
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants.staggered_native import StaggeredLane
from . import arrival_queue as pace
from .full_v5_check import _sha

CASE, MAIN, HELPER = "DS26-0197", 0, 1
ROLES = ("pruned", "dense")
METHOD = "native_pruning_whole_four"
MODULE = "tools.pipeline_eval.qualification.native_pruning_whole"
REPORT = ROOT / "reports/2026_11_19_receiver_screening/pilot-influence/pruning-whole"
LOCAL = REPORT.with_name("native-pruning")
ASSETS = Path("/var/tmp/leo-native-pruning-20261119/build")
DETECTOR = "libleo-adaptive-detector.so.1"
JOIN = "libleo-staggered-native.so"
STAGES = ("coarse", "proposal", "fine_fft", "conditioned", "glrt", "fractional_epoch")


def freeze(work):
    if work.exists() or (REPORT / "source-lock.json").exists():
        raise FileExistsError("a full active-set replay is already frozen")
    seal = whole_iq.read(LOCAL / "result-lock.json")["files"]
    feature = whole_iq.read(
        whole_iq.checked(LOCAL / "feature-gate.json", seal["feature-gate.json"])
    )
    if not feature["passed"] or not feature["matched_science"] or len(feature["cases"]) != 2:
        raise ValueError("exact saved-IQ local qualification did not pass")
    parent = pace.REPORT / "stage-lock.json"
    archived = whole_iq.read(parent)["files"]
    source = whole_iq.checked(pace.REPORT / "source-lock.json", archived["source-lock.json"])
    case = whole_iq.read(source)["cases"][CASE]
    reference = case["modes"]["control"]
    events = whole_iq.checked(pace.REPORT / reference["events"], reference["sha256"])
    whole_iq.checked(events, archived[events.name])
    original = pace.PARENT / "prediction-lock.json"
    stock = whole_iq.read(original)["files"]
    stock_source = whole_iq.checked(pace.PARENT / "source-lock.json", stock["source-lock.json"])
    physical = whole_iq.read(stock_source)["cases"][CASE]
    if (
        case["capture"]["input_manifest_sha256"] != physical["clock_authority"]
        or case["capture"]["case"]["recording"] != physical["recording"]
    ):
        raise ValueError("matched stock clocks changed physical capture")
    work.mkdir(parents=True)
    write(REPORT / events.name, events.read_bytes())
    assets = {}
    for role, label in (("pruned", "candidate"), ("dense", "control")):
        for leaf in (JOIN, DETECTOR):
            digest = feature[label][leaf]["sha256"] if role == "pruned" else feature[label][leaf]
            expected = whole_iq.checked(ASSETS / label / leaf, digest)
            assets[f"{role}:{leaf}"] = dict(path=str(expected), sha256=digest)
    programs = (
        Path(__file__),
        Path(pace.__file__),
        ROOT / "tools/pipeline_eval/variants/staggered_native.py",
        REPORT / "PROTOCOL.md",
        parent,
        source,
        original,
        stock_source,
        LOCAL / "feature-gate.json",
    )
    lock = REPORT / "source-lock.json"
    save_json(
        lock,
        dict(
            cases={CASE: dict(case, cpu=MAIN, modes={role: reference for role in ROLES})},
            assets=assets,
            programs={str(p): _sha(p) for p in programs},
            cpus=[MAIN, HELPER],
            order=list(ROLES),
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            limit_s=pace.LIMIT_S,
            parent_prediction_sha256=_sha(original),
            stock_source_sha256=_sha(stock_source),
            historical_pace=dict(
                cpu=case["cpu"], mode="control", timing="archived separate wall service"
            ),
        ),
    )
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(lock)))


@contextmanager
def configuration(attempt=None):
    original = pace.native_visit
    thread = local()
    stage = []

    def bind(capture, mode, assets, stack):
        def item(name):
            row = assets[f"{mode}:{name}"]
            return whole_iq.checked(Path(row["path"]), row["sha256"])

        lib = item(JOIN)
        core = item(DETECTOR)
        port = stack.enter_context(StaggeredLane(lib, capture["edge"], helper_cpu=HELPER))
        if str(core) not in Path("/proc/self/maps").read_text():
            raise ValueError("the paced process loaded the wrong detector library")

        def detect(samples):
            output, timing = port.analyze(samples, "stock", trace=True)
            a, b = timing["lanes"]
            if (a["cpu"], b["cpu"]) != (MAIN, HELPER) or (a["hint"], b["hint"]) != (-1, -1):
                raise ValueError("raw replay left the exact four-on-both dual-CPU route")
            thread.helper = b["cpu_ns"]
            thread.numeric = {
                key: sum(getattr(row, key + "_ms") for row in port.out.rows[:2]) for key in STAGES
            }
            return output

        return detect

    def visit(frame, analyze, detect, policy):
        thread.helper, thread.numeric = 0, None
        packet, (wall, cpu) = original(frame, analyze, detect, policy)
        if thread.numeric is not None:
            stage.append(dict(visit=packet["visit"], **thread.numeric))
        return packet, (wall, cpu + thread.helper)

    with patch.multiple(
        pace, CPUS={CASE: MAIN}, MODES=ROLES, MODULE=MODULE, build_native=bind, native_visit=visit
    ):
        yield
    if attempt:
        target = attempt / "native-stages.json.gz"
        pace.writegz(target, sorted(stage, key=lambda r: r["visit"]))
        target.chmod(0o644)


def replay(work):
    with configuration():
        pace.replay(work, REPORT)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("freeze", "replay", "worker"))
    p.add_argument("work", type=local_output)
    args = p.parse_args()
    if args.mode == "worker":
        with configuration(args.work):
            pace.execute(args.work)
    else:
        {"freeze": freeze, "replay": replay}[args.mode](args.work)
