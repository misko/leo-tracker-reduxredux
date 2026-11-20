"""Measure the existing strict fractional partner-on-hit rule in the stock arrival FIFO."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from threading import local
from types import SimpleNamespace
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants.staggered_native import RfStagger
from . import arrival_queue as pace
from . import equal_pace as old
from . import paced_controlled_source as external
from . import second_on_miss_whole_raw as conditional
from .full_v5_check import _sha
from .on_hit_waveforms_raw import needs_partner

CASE = external.CASE
REPORT = old.SCREEN / "antenna-confirmation/paced-hit"
WORK = Path("/var/tmp/leo-paced-hit-20261119")
SOURCE = Path("/dev/shm/leo-paced-hit-20261119")
UNIT = "leo-paced-hit-source.service"
MODULE = "tools.pipeline_eval.qualification.paced_hit"
DUAL, HIT = "dual", "hit"
ORDER = (DUAL, HIT)
MAIN, STAGING = 10, 11
STOCK = Path("/var/tmp/leo-on-hit-waveforms-20261119/libraries/DS29-0174/wide-stock.so")
WIDE_SHA = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"


def earliest():
    path = whole_iq.checked(old.REPORT / "source-lock.json", external.OLD_SHA)
    return whole_iq.read(path)["cases"][CASE]


def reference():
    (doc, stock, logical), _ = old.references(CASE)
    return doc, stock, logical


def projection(packet, primary):
    from ..variants.second_on_miss import needs_partner as misses

    if [p["receiver_id"] for p in packet["probes"]] != [0, 1]:
        raise ValueError("the projected stock packet needs both ordered physical slots")
    hit = not misses(packet["probes"][primary])
    probes = (
        packet["probes"]
        if hit
        else [
            dict(probe, candidates=[]) if rx != primary else probe
            for rx, probe in enumerate(packet["probes"])
        ]
    )
    return dict(packet, probes=probes), hit


def events(doc, stock):
    rows = [dict(row, full_visit_sha256=pace.fingerprint(row)) for row in stock]
    events = pace.reference_events(doc, rows)
    turn = RfStagger()
    output = {role: [] for role in ORDER}
    for event, packet in zip(events, stock, strict=True):
        primary, center, hit = None, None, None
        seen = packet
        if event["status"] == "processed":
            a, b = packet["probes"]
            center = int(a["actual_rf_hz"])
            if center != a["actual_rf_hz"] or center != b["actual_rf_hz"]:
                raise ValueError("stock physical lanes did not share an exact RF center")
            primary = turn.reserve(center)
            seen, hit = projection(packet, primary)
        common = dict(event, center_hz=center, primary_receiver=primary, primary_hit=hit)
        output[DUAL].append(dict(common, measured_lanes=2 if primary is not None else 0))
        output[HIT].append(
            dict(
                common,
                full_visit_sha256=pace.fingerprint(seen),
                measured_lanes=(1 + hit) if primary is not None else 0,
            )
        )
    return output


def freeze():
    path = REPORT / "detector-lock.json"
    if path.exists():
        raise FileExistsError("the direct hit gate comparison is already frozen")
    doc, stock, logical = reference()
    original = earliest()
    if doc["source"]["raw_recording_authority_digest"] != original["raw_recording_sha256"]:
        raise ValueError("the two candidate regimes require the same original IQ")
    branches = {}
    for role, rows in events(doc, stock).items():
        name = f"{role}-events.json.gz"
        pace.writegz(REPORT / name, rows)
        branches[role] = dict(events=name, sha256=_sha(REPORT / name))
    source_files = (
        Path(__file__),
        Path(pace.__file__),
        Path(conditional.__file__),
        Path(external.__file__),
        ROOT / "tools/pipeline_eval/qualification/on_hit_waveforms_raw.py",
        ROOT / "tools/pipeline_eval/qualification/on_hit_waveforms.py",
        ROOT / "tools/pipeline_eval/variants/second_on_miss.py",
        ROOT / "tools/pipeline_eval/variants/single_chain.py",
        REPORT / "PROTOCOL.md",
    )
    save_json(
        path,
        dict(
            cases={CASE: dict(original, cpu=MAIN, modes=branches)},
            id=CASE,
            order=ORDER,
            original_clock_source_sha256=external.OLD_SHA,
            original_stock_prediction_sha256=old.STOCK_SHA,
            stock_logical_sha256=logical,
            cpus=[MAIN, STAGING],
            waiting_slots=1,
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            limit_s=pace.LIMIT_S,
            assets={"stock": dict(path=str(whole_iq.checked(STOCK, WIDE_SHA)), sha256=WIDE_SHA)},
            programs={str(p.relative_to(ROOT)): _sha(p) for p in source_files},
        ),
    )


def stage():
    with patch.multiple(external, REPORT=REPORT, UNIT=UNIT), patch.object(old, "MAIN", STAGING):
        external.start(SOURCE)


def activate(work):
    plan = whole_iq.read(REPORT / "detector-lock.json")
    ready = whole_iq.read(SOURCE / "ready.json")
    spec = plan["cases"][CASE]
    group = ready["end"]["cgroup"]
    if (
        ready["case"] != CASE
        or ready["raw_recording_sha256"] != spec["raw_recording_sha256"]
        or external.charge(group)["memory.stat.shmem"] < ready["bytes"]
    ):
        raise ValueError("predecoded source failed its original-case or residency binding")
    for name in ("ready.json", "members.json.gz"):
        write(REPORT / name, (SOURCE / name).read_bytes())
    spec.update(source=str(SOURCE), ready_sha256=_sha(REPORT / "ready.json"))
    plan.update(external_cgroup=group)
    work.mkdir(parents=True, exist_ok=False)
    save_json(REPORT / "source-lock.json", plan)
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(REPORT / "source-lock.json")))


@contextmanager
def configuration(plan, ledger):
    state = local()
    native_visit = pace.native_visit

    def detector(capture, mode, assets, stack):
        import numpy as np

        from leo.analysis.starlink.native_short_window import NativeShortWindow
        from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

        got = assets["stock"]
        lib = whole_iq.checked(Path(got["path"]), got["sha256"])
        edge, fs = capture["edge"], 10_000_000
        exact = np.asarray(qin_edge_pilot_frame(fs, edge), dtype="<c16")
        control = np.asarray(
            qin_edge_pilot_frame(fs, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
        )
        port = stack.enter_context(
            NativeShortWindow(
                str(lib),
                exact,
                control,
                sample_rate_hz=fs,
                receiver_count=2 if mode == DUAL else 1,
                fractional_epoch=True,
            )
        )
        if mode == DUAL:
            return port.analyze
        if mode != HIT:
            raise ValueError("unsupported direct hit trace branch")

        def hit(samples):
            row = state.event
            result, partner = conditional.detect(port, samples, row["primary_receiver"])
            if type(partner) is not bool or partner != row["primary_hit"]:
                raise ValueError("actual gate failed its independent full-fractional projection")
            return result

        return hit

    def visit(frame, analyze, detect, policy):
        w = frame[1]
        row = ledger[int(w.acquisition["global_visit"])]
        if row["center_hz"] is not None and row["center_hz"] != w.target["rf_center_hz"]:
            raise ValueError("actual RF differs from the predeclared alternating primary metadata")
        state.event = row
        return native_visit(frame, analyze, detect, policy)

    def packets(capture, verified):
        if capture != plan["case"]["capture"] or verified:
            raise ValueError("local staging may serve only its bound physical recording")
        yield from external.packets(Path(plan["case"]["source"]))

    with (
        patch.object(conditional, "second_on_miss", SimpleNamespace(needs_partner=needs_partner)),
        patch.multiple(
            pace, MODULE=MODULE, build_native=detector, native_visit=visit, packets=packets
        ),
        patch.object(pace.iq_service, "MODULE", MODULE),
    ):
        yield


def worker(attempt):
    plan = whole_iq.read(attempt / "plan.json")
    spec = plan["case"]
    ready = whole_iq.read(
        whole_iq.checked(Path(spec["source"]) / "ready.json", spec["ready_sha256"])
    )
    if ready["raw_recording_sha256"] != spec["raw_recording_sha256"]:
        raise ValueError("live action requested a different source recording")
    ledger = pace.readgz(whole_iq.checked(attempt / "events.json.gz", plan["events_sha256"]))
    with configuration(plan, ledger):
        pace.execute(attempt)


def run(work):
    plan = pace.plan(work, REPORT)
    if plan["order"] != list(ORDER):
        raise ValueError("matched branch order differs from the frozen design")
    with patch.object(pace, "MODULE", MODULE), patch.object(pace.iq_service, "MODULE", MODULE):
        for role in ORDER:
            group = plan["external_cgroup"]
            stats = dict(start=external.charge(group))
            pace.launch(work / CASE / role, plan["cases"][CASE], role, plan["assets"], REPORT)
            stats["end"] = external.charge(group)
            save_json(REPORT / f"raw/{role}/source-charge.json", stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "stage", "activate", "run", "worker"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    args = parser.parse_args()
    if args.action in ("freeze", "stage"):
        {"freeze": freeze, "stage": stage}[args.action]()
    else:
        {"activate": activate, "run": run, "worker": worker}[args.action](args.work)
