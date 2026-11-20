"""Run fused four and staggered mixed on one matched archived delivery clock."""

import argparse
import csv
from contextlib import contextmanager
from pathlib import Path
from threading import local
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants.dual_lane import DualLane
from ..variants.staggered_native import RfStagger, StaggeredLane
from . import arrival_queue as pace
from . import capture_release, recording_to_v5
from .full_v5_check import _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
BASE = SCREEN / "latency-and-support"
REPORT = SCREEN / "receiver-choice/equal-pace"
WORK = Path("/var/tmp/leo-equal-pace-20261119")
COMBINED = Path("/var/tmp/leo-combined-native-20261119/build")
STAGGERED = Path("/var/tmp/leo-staggered-native-20261119/build")
MODULE = "tools.pipeline_eval.qualification.equal_pace"
FOUR, MIXED = "fused-four", "staggered"
MAIN, HELPER = 22, 23
EXCLUDED = {"DS26-0026", "DS29-0316"}
POOL_SHA = "2bc3768d2c146adc402992f5bbb5714119c2be77ec1959fa6c16329bdebef73a"
TIMING_SHA = "1883d6e3adb14fc06485d10f7de68fa93a0d995fff6f7517444d4b6bb6e15255"
STOCK_SHA = "42136b7b48d910bf416772d7c7eb9e127dafb0ee5f54089c58d94820a05a9872"
FIFTH_SHA = "69d037211e35688d7321f21c1f89b235880e5118cc4c8af421c43099f3925e42"
FUSED_BUILD_SHA = "330e5b3736182adb7a8417638c553ee78b1500b354bb5495dbc9ff1353f93a88"
MIXED_BUILD_SHA = "7011f777eadf8027e64b2582d57ba3034622ca42ecbbd33a736770326d5bd597"
CORE = "libleo-adaptive-detector.so.1"


def choose(ids, bindings):
    if len(set(ids)) != 20 or set(ids) != bindings.keys() or not bindings.keys() >= EXCLUDED:
        raise ValueError("incomplete sealed 20-recording clock roster")
    ident = min(set(ids) - EXCLUDED, key=lambda value: (bindings[value], value))
    order = [MIXED, FOUR] if int(bindings[ident][-1], 16) % 2 else [FOUR, MIXED]
    return ident, order


def comparable(left, right):
    return {k: v for k, v in left.items() if k != "probes"} == {
        k: v for k, v in right.items() if k != "probes"
    } and [{k: v for k, v in probe.items() if k != "candidates"} for probe in left["probes"]] == [
        {k: v for k, v in probe.items() if k != "candidates"} for probe in right["probes"]
    ]


def projected_rows(doc, stock, fifth):
    physical = [dict(row, full_visit_sha256=pace.fingerprint(row)) for row in stock]
    base = pace.reference_events(doc, physical)
    turn = RfStagger()
    fused, staggered = [], []
    for event, left, right in zip(base, stock, fifth, strict=True):
        if not comparable(left, right):
            raise ValueError("whole-IQ references disagree on acquisition envelope")
        center, lane, mixed = None, None, left
        if event["status"] == "processed":
            a, b = left["probes"]
            center = int(a["actual_rf_hz"])
            if center != a["actual_rf_hz"] or a["actual_rf_hz"] != b["actual_rf_hz"]:
                raise ValueError("native probes must agree on an integer physical RF center")
            lane = turn.reserve(center)
            mixed = dict(
                left,
                probes=[
                    right["probes"][rx] if rx == lane else probe
                    for rx, probe in enumerate(left["probes"])
                ],
            )
        fused.append(dict(event, fifth_lane=None, center_hz=center))
        staggered.append(
            dict(
                event, fifth_lane=lane, center_hz=center, full_visit_sha256=pace.fingerprint(mixed)
            )
        )
    return {FOUR: fused, MIXED: staggered}


def references(ident):
    from . import fifth_completion
    from .exact_wide_iq_results import detector_rows
    from .fifth_completion_results import native_data
    from .fresh_replay_results import sealed

    stock = SCREEN / "receiver-core/full-stride"
    new = fifth_completion.REPORT
    a, b = (
        sealed(stock, "prediction-lock.json", STOCK_SHA),
        sealed(new, "prediction-lock.json", FIFTH_SHA),
    )
    witness = whole_iq.read(stock / "resources.json")[ident]["control"]
    first = Path(witness["service"]["binding"]["attempt"])
    whole_iq.checked(first / "plan.json", witness["service"]["binding"]["plan_sha256"])
    whole_iq.checked(first / "service.log", witness["service"]["log_sha256"])
    second = fifth_completion.WORK / ident / "candidate"
    measured = whole_iq.read(new / f"attempts/{ident}.json")
    whole_iq.checked(second / "raw.json", measured["authority"]["raw_receipt_sha256"])
    data = []
    for folder, seal, root, branch in ((first, a, stock, "control"), (second, b, new, "candidate")):
        raw = whole_iq.read(folder / "raw.json")
        name = f"native/{branch}/{ident}.json.gz"
        path = whole_iq.checked(root / name, seal["files"][name])
        doc = native_data(path, raw["native_sha256"].removeprefix("sha256:"))
        visits, _, logical = detector_rows(folder)
        probes = [p for row in visits for p in row["probes"]]
        if probes != doc["source"]["probes"] or any(
            row["delivery_clock"] != clock
            for row, clock in zip(visits, doc["delivery_clocks"], strict=True)
        ):
            raise ValueError("whole-IQ envelope differs from authenticated native reference")
        data.append((doc, visits, logical))
    return data


def assets():
    result = {}
    tests = (
        (FOUR, COMBINED, FUSED_BUILD_SHA, "libleo-dual-lane.so"),
        (MIXED, STAGGERED, MIXED_BUILD_SHA, "libleo-staggered-native.so"),
    )
    for role, directory, digest, name in tests:
        build = whole_iq.read(whole_iq.checked(directory / "build.json", digest))
        for key, library in ((role, name), (role + "-core", CORE)):
            sha = build["files"][library]
            result[key] = dict(path=str(whole_iq.checked(directory / library, sha)), sha256=sha)
    if result[FOUR + "-core"]["sha256"] != result[MIXED + "-core"]["sha256"]:
        raise ValueError("the two paced paths must share the same native detector core")
    return result


def freeze(work):
    from .fresh_replay_results import sealed

    if work.exists() or (REPORT / "source-lock.json").exists():
        raise FileExistsError("equal-pace comparison is already declared")
    pool = sealed(BASE / "complete-roster", "all-figure-lock.json", POOL_SHA)
    sealed(BASE / "complete-timing", "prediction-lock.json", TIMING_SHA)
    with (BASE / "complete-timing/resources.csv").open() as table:
        manifest = {
            r["id"]: r["clock_authority"]
            for r in csv.DictReader(table)
            if r["method"] == "complete_four_regions"
        }
    ident, order = choose(pool["cases"], manifest)
    case, _ = whole_iq.binding(ident)
    capture = dict(capture_release.read_capture(case), case=case)
    if capture["input_manifest_sha256"] != manifest[ident]:
        raise ValueError("recording manifest differs from the metadata-only selection")
    (doc, stock, stock_logical), (other, fifth, mixed_logical) = references(ident)
    chain = doc["source"]["raw_recording_authority_digest"]
    if chain != other["source"][
        "raw_recording_authority_digest"
    ] or chain != recording_to_v5.digest([manifest[ident], [row["iq_sha256"] for row in stock]]):
        raise ValueError("whole-IQ native reference input sample hash chain changed")
    modes = {}
    for role, events in projected_rows(doc, stock, fifth).items():
        name = f"{role}-events.json.gz"
        pace.writegz(REPORT / name, events)
        modes[role] = dict(events=name, sha256=_sha(REPORT / name))
    names = (
        Path(__file__),
        Path(pace.__file__),
        Path(recording_to_v5.__file__),
        Path(capture_release.__file__),
        REPORT / "PROTOCOL.md",
        ROOT / "tools/pipeline_eval/variants/staggered_native.py",
        ROOT / "tools/pipeline_eval/variants/dual_lane.py",
    )
    spec = dict(
        capture=capture,
        cpu=MAIN,
        producer=str(capture_release.producer(case, capture).root),
        raw_recording_sha256=chain,
        modes=modes,
    )
    save_json(
        REPORT / "source-lock.json",
        dict(
            case=ident,
            order=order,
            cpus=[MAIN, HELPER],
            cases={ident: spec},
            programs={str(p): _sha(p) for p in names},
            assets=assets(),
            pool_sha256=POOL_SHA,
            timing_sha256=TIMING_SHA,
            references=[STOCK_SHA, FIFTH_SHA],
            manifest=manifest,
            raw_logical_sha256=[stock_logical, mixed_logical],
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            waiting_slots=1,
            limit_s=pace.LIMIT_S,
        ),
    )
    work.mkdir(parents=True, exist_ok=False)
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(REPORT / "source-lock.json")))
    print(ident, order, flush=True)


@contextmanager
def configure(attempt=None):
    state = local()
    original = pace.native_visit
    events = pace.readgz(attempt / "events.json.gz") if attempt is not None else ()

    def detector(capture, mode, bindings, stack):
        library = bindings[mode]
        lib = whole_iq.checked(Path(library["path"]), library["sha256"])
        core = bindings[mode + "-core"]
        whole_iq.checked(Path(core["path"]), core["sha256"])
        cls = StaggeredLane if mode == MIXED else DualLane
        native = stack.enter_context(cls(lib, capture["edge"], helper_cpu=HELPER))

        def detect(samples):
            if mode == MIXED:
                result, profile = native.mixed(samples, state.event["fifth_lane"], trace=True)
            else:
                result, profile = native.analyze(samples, "stock", trace=True)
            caller, helper = profile["lanes"]
            if (caller["cpu"], helper["cpu"]) != (MAIN, HELPER):
                raise ValueError("native calls departed from the frozen CPU pair")
            state.helper = helper["cpu_ns"]
            return result

        return detect

    def visit(frame, analyze, detect, policy):
        window = frame[1]
        row = events[int(window.acquisition["global_visit"])]
        if row["center_hz"] is not None and row["center_hz"] != window.target["rf_center_hz"]:
            raise ValueError("recorded target center differs from the frozen selector input")
        state.event, state.helper = row, 0
        packet, (wall, cpu) = original(frame, analyze, detect, policy)
        return packet, (wall, cpu + state.helper)

    with (
        patch.multiple(pace, MODULE=MODULE, build_native=detector, native_visit=visit),
        patch.object(pace.iq_service, "MODULE", MODULE),
    ):
        yield


def run(work):
    plan = pace.plan(work, REPORT)
    ident = plan["case"]
    with configure():
        for role in plan["order"]:
            pace.launch(work / ident / role, plan["cases"][ident], role, plan["assets"], REPORT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    args = parser.parse_args()
    if args.action == "worker":
        with configure(args.work):
            pace.execute(args.work)
    else:
        {"freeze": freeze, "run": run}[args.action](args.work)
