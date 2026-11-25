"""Run the separately registered 40-second rank-68 saved position comparison."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
from shutil import copytree
import sys
from time import time_ns
from unittest.mock import patch

WORKER = Path(__file__).resolve()
sys.path.insert(0, str(WORKER.parent))

import ds30_0280_moment_position_transfer as transfer  # noqa: E402
from ds30_0280_moment_position_transfer import capsule, held, replay, saved, scoring  # noqa: E402

STEM = "ds30-0280-moment-position-extended"
PROTOCOL_PIN = "1c88c56ae3562e4ec40d9af0d14d8f9415ad85d50b6cad67e680dad254936f99"
REFUSAL = "measurements/ds30-0280-moment-position-disposition.json"
REFUSAL_PIN = "4b665049d5d285e88fa637e3f55fa5395a33829866b145b8cec644e07399be78"
PREVIOUS = Path("/tmp/leo-v3-0280-moment-transfer02")
PREVIOUS_PIN = "d210c281fb030f270b888638ac42b02cf32ca819f58c1425753bc0e9687652ee"
LIMIT_S = 40
BASE_LIVE = capsule.live_window
BASE_LEASE = capsule.lease


def experiment(*, probe):
    spec = transfer.experiment(probe=probe)
    spec.stem = STEM
    spec.source = WORKER.name
    spec.transfer_sources += (transfer.WORKER.name, REFUSAL)
    return spec


def check_registration():
    if saved.protocol(experiment(probe=False)) != PROTOCOL_PIN:
        raise ValueError("The blinded 40-second protocol changed")
    return saved.document(WORKER.parent/REFUSAL, REFUSAL_PIN)


def fresh_window(event, pid, after_ns):
    # Use the original case, event digest, driver-idle and freshness checks.
    # The separate protocol permits spanning the driver's first scheduled retry.
    with patch.object(capsule, "TIMEOUT", 21):
        BASE_LIVE(event, pid)
    if event["unix_ns"] <= after_ns:
        raise ValueError("The official driver has not retried since ordinary release")


@contextmanager
def observed_lease(window):
    try:
        with BASE_LEASE() as fd:
            window["acquired_ns"] = time_ns()
            yield fd
    finally:
        if "acquired_ns" in window:
            window["released_ns"] = time_ns()


@contextmanager
def ports(run, row, candidate, *, after_ns=0, window=None):
    with transfer.ports(run, row, candidate), patch.object(held, "experiment", experiment), patch.multiple(
            capsule, WORKER=WORKER, TIMEOUT=LIMIT_S,
            live_window=lambda event, pid: fresh_window(event, pid, after_ns),
            lease=BASE_LEASE if window is None else lambda: observed_lease(window)):
        yield


def prepare(run, row):
    refused = check_registration()
    previous = saved.document(PREVIOUS/"rank68-readiness.json", PREVIOUS_PIN)
    state = replay.status(row)
    if (not state["verified_pair"] or state["pair_sha256"] != previous["state"]
            or refused["official_pair"] != previous["state"] or refused["preparation"] != previous
            or saved.document(PREVIOUS/"field/ordinary/clock.json", refused["attempts"][-1]["clock_sha256"])["exit_code"] != 124
            or (PREVIOUS/"field/corrected/worker-intent.json").exists()):
        raise ValueError("The frozen verified pair or admitted infrastructure refusal changed")
    if run.parent != Path("/tmp") or run.resolve() != run or run.exists():
        raise ValueError("Require a fresh direct /tmp tmpfs output root")
    run.mkdir(mode=0o700)
    root = run/"field"
    root.mkdir(mode=0o700)
    transfer.mount_root(run).mkdir(mode=0o700)
    stage = root/"stage"
    copytree(PREVIOUS/"field/stage", stage, copy_function=os.link, symlinks=False)
    spec = experiment(probe=False)
    plans, ready = {}, {}
    for mode, original_plan_pin in previous["plans"].items():
        original = PREVIOUS/"field"/mode
        cell = root/mode
        cell.mkdir(mode=0o700)
        for name in ("admission.json", "derived-native.json"):
            os.link(original/name, cell/name)
        plan = saved.document(original/"plan.json", original_plan_pin)
        plan.update(stage=str(stage), protocol=PROTOCOL_PIN, sources=saved.source_pins(spec))
        plans[mode] = pin = saved.write(cell/"plan.json", plan)
        with ports(run, row, plan["moment_candidate"]):
            ready[mode] = capsule.preflight(cell, pin, mode, replay.OBSERVER_PIN)
    return saved.write(run/"extended-ready.json", dict(field_pair=state["pair_sha256"],
        previous_ready_sha256=PREVIOUS_PIN, referral_sha256=REFUSAL_PIN, plans=plans, readiness=ready,
        cap_s=LIMIT_S, protocol_sha256=PROTOCOL_PIN, new_archive_bytes=0, waveform_reads=0))


def retry_readout(campaign, event, window):
    """Read official event metadata only for the case that supplied the lease window."""
    acquired, released = window["acquired_ns"], window["released_ns"]
    delay_events, next_event = [], None
    for path in sorted((campaign/"cases"/event["case"]/"events").glob("*.json")):
        stamp = int(path.name.split("-", 1)[0])
        if stamp < acquired:
            continue
        state = saved.document(path)["state"]
        entry = dict(unix_ns=stamp, state=state, event=str(path.relative_to(campaign)),
                     sha256=saved.identifier(path))
        if stamp <= released and state == "deferred_shared_lease":
            delay_events.append(entry)
        if stamp > released:
            next_event = entry
            break
    return dict(retries_deferred_by_shared_lease=delay_events, next_official_event=next_event)


def watch(run, row, mode, pin, driver_pid, ordinary_gate):
    root = run/"field"
    cell = root/mode
    ready = saved.document(run/"extended-ready.json", pin)
    plan = saved.document(cell/"plan.json", ready["plans"][mode])
    after_ns = 0
    if mode == "corrected":
        ordinary = saved.document(root/"ordinary-gate.json", ordinary_gate)
        release = saved.document(root/"ordinary/lease-observation.json")
        if release["clock_sha256"] != ordinary["ordinary"]["clock"]:
            raise ValueError("Ordinary release does not bind the verified child clock")
        after_ns = release["released_ns"]
    window = {}
    try:
        with ports(run, row, plan["moment_candidate"], after_ns=after_ns, window=window):
            return capsule.watch(root, mode, driver_pid, ready["readiness"][mode], ordinary_gate)
    finally:
        if (cell/"clock.json").exists():
            intent = saved.document(cell/"worker-intent.json")
            event = intent["event"]["event"]
            readout = retry_readout(held.CAMPAIGN, event, window)
            saved.write(cell/"lease-observation.json", dict(window, **readout, trigger=event,
                clock_sha256=saved.identifier(cell/"clock.json"), prior_ordinary_release_ns=after_ns or None))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("prepare", "watch", "child", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--pin")
    cli.add_argument("--cell", choices=capsule.CELLS)
    cli.add_argument("--driver-pid", type=int)
    cli.add_argument("--ordinary-gate-pin")
    cli.add_argument("--probe-only", action="store_true")
    args = cli.parse_args()
    run = args.root
    if not run.is_relative_to("/tmp") or run.resolve() != run:
        cli.error("Use the verified private /tmp root")
    check_registration()
    row = transfer.enrollment()
    if args.mode == "child" and args.pin and args.cell:
        plan = saved.document(run/"plan.json", args.pin)
        if args.probe_only:
            transfer.verify_archive_mount(run, plan)
        with ports(run.parents[1], row, plan["moment_candidate"]), transfer.optional_projection(args.cell):
            capsule.child(run, args.pin, args.cell, probe_only=args.probe_only)
        return 0
    sys.addaudithook(saved.deny_backing)
    if args.mode == "prepare":
        result = prepare(run, row)
    elif args.mode == "watch" and args.pin and args.cell and args.driver_pid:
        result = watch(run, row, args.cell, args.pin, args.driver_pid, args.ordinary_gate_pin)
    elif args.mode == "score" and args.pin:
        root = run/"field"
        closure = saved.document(root/"pair-verified-before-survey.json", args.pin)
        pins = saved.document(root/"verification-pins.json", closure["closure_sha256"])
        plan = saved.document(root/"corrected/plan.json", pins["corrected"]["plan"])
        with ports(run, row, plan["moment_candidate"]):
            return scoring.verify(root, pins)
    else:
        cli.error("Require the matched role, pinned readiness and live driver, or both sealed publications")
    if isinstance(result, int):
        return result
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
