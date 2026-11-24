"""Admit the single sealed joint DS30-0049 saved worker without queueing."""

import argparse
import fcntl
import os
import runpy
import signal
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from shutil import copyfile
from time import monotonic, perf_counter_ns, sleep, time_ns

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matched_donor_0049_trial as trial  # noqa: E402
from joint_recovery_0049_admission import QUIET, QUIET_PIN, device_stats  # noqa: E402
from joint_recovery_0049_direct import (  # noqa: E402
    DRIVER,
    PLAN_PIN,
    WATCH_PIN,
    require_cached,
)

DURATION_S = 720
CHILD_LIMIT_S = 18
OLD_DIRECT = "70f31eaf090d96b43e9117c03df413e5fb9f841fca7c9c91647c92fee8d33995"
ROOT = Path("/dev/shm/leo-v3-joint-recovery-0049-02")
INPUTS = Path("/dev/shm/leo-v3-joint-recovery-0049-01")


@contextmanager
def lease():
    with trial.LOCK.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield lock.fileno()


def observe_quiet(scope, devices, guards):
    states = {name: scope["sample"](path, monotonic) for name, path in devices.items()}
    ready = [guards[name].observe(state) for name, state in states.items()]
    return all(ready), {
        name: dict(asdict(state), queue_mean=guards[name].queue_mean,
                   interval_full_pct=guards[name].current_full)
        for name, state in states.items()
    }


def wait_for_slot(*, deadline, sleep_until, sample, driver_idle, use_lease, cached, launch):
    counts = Counter()
    latest = {}
    while monotonic() < deadline:
        ready, latest = sample()
        if not ready:
            counts["nonquiet"] += 1
        elif not driver_idle():
            counts["official_busy"] += 1
        else:
            with ExitStack() as stack:
                try:
                    fd = stack.enter_context(use_lease())
                except BlockingIOError:
                    counts["lease_busy"] += 1
                else:
                    ready, latest = sample()
                    if not ready:
                        counts["lost_quiet_on_lease"] += 1
                    elif not driver_idle():
                        counts["official_busy_on_lease"] += 1
                    elif monotonic() < deadline:
                        cache = cached()
                        ready, latest = sample()
                        if not ready or not driver_idle() or monotonic() >= deadline:
                            counts["changed_during_cache_check"] += 1
                        else:
                            admission = dict(quiet=latest, cache=cache, rejected_polls=dict(counts))
                            return launch(fd, admission), counts, latest
        sleep_until(deadline)
    return None, counts, latest


def run_child(root, fd, admission, machine, *, binding=None):
    worker = HERE/"matched_donor_0049_trial.py"
    if binding is None:
        binding = dict(driver=worker, plan_pin=PLAN_PIN, protocol=trial.protocol(trial.JOINT),
                       budget=CHILD_LIMIT_S, flags=[trial.JOINT.option])
    scratch = root/"scratch"
    scratch.mkdir()
    font = trial.STAGE/"centroid-scratch/fontlist-v3.11.0.json"
    if font.is_file():
        copyfile(font, scratch/font.name)
    env = os.environ | dict(TMPDIR=str(scratch), MPLCONFIGDIR=str(scratch),
                            XDG_CACHE_HOME=str(scratch))
    command = [sys.executable, "-IB", str(binding["driver"]), "worker", str(root),
               "--pin", binding["plan_pin"], *binding["flags"], "--lease-fd", str(fd)]
    trial.write(root/"child-intent.json", dict(
        command=command, decision_unix_ns=time_ns(), admission=admission, source=trial.identifier(worker),
    ))
    with (root/"worker.stdout").open("x") as out, (root/"worker.stderr").open("x") as err:
        before, start, unix = getrusage(RUSAGE_CHILDREN), perf_counter_ns(), time_ns()
        with subprocess.Popen(command, env=env, stdout=out, stderr=err, pass_fds=(fd,),
                              start_new_session=True, stdin=subprocess.DEVNULL) as child:
            print(f"Started the sole joint worker {child.pid}", flush=True)
            try:
                status = child.wait(binding["budget"])
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                status = 124
        after, end = getrusage(RUSAGE_CHILDREN), perf_counter_ns()
    clock = trial.write(root/"clock.json", dict(
        command=command, elapsed_s=(end-start)*1e-9, exit_code=status,
        cpu_s=(after.ru_stime+after.ru_utime)-(before.ru_stime+before.ru_utime),
        started_unix_ns=unix, finished_unix_ns=time_ns(),
        io_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt,
        official_idle_admission=admission,
    ))
    seal = trial.write(root/"prediction-seal.json", dict(
        clock=clock, receipt=trial.identifier(root/"receipt.json") if status==0 else None,
        machine=machine, plan_sha256=binding["plan_pin"], protocol=binding["protocol"],
        source=trial.identifier(worker), survey_reads=0, waveform_reads=0,
    ))
    return dict(exit_code=status, clock_sha256=clock, prediction_sha256=seal)


def prepare(root):
    previous = trial.document(INPUTS/"watch.json", WATCH_PIN)
    direct = trial.document(INPUTS/"direct-admission.json", OLD_DIRECT)
    previous_products = ("worker.stdout", "clock.json", "prediction-seal.json")
    if (previous["plan_sha256"] != PLAN_PIN or direct["plan_sha256"] != PLAN_PIN
            or direct["worker_started"] or any((INPUTS/p).exists() for p in previous_products)):
        raise ValueError("The original participant must have a pinned, unstarted saved solve")
    plan = trial.document(INPUTS/"plan.json", PLAN_PIN)
    if (plan["protocol"] != trial.protocol(trial.JOINT)
            or plan["worker"] != trial.identifier(HERE/"matched_donor_0049_trial.py")
            or plan["sources"] != trial.source_pins(trial.JOINT)):
        raise ValueError("The original protocol, worker or source bytes differ")
    root.mkdir(mode=0o700)
    for name, pin in (("plan.json", PLAN_PIN),
                      ("derived-native.json", plan["change"]["derived_native_sha256"])):
        source = INPUTS/name
        trial.document(source, pin)
        dest = root/name
        copyfile(source, dest)
        dest.chmod(0o400)
        trial.document(dest, pin)


def slot_inputs(pid, duration):
    if not 0 < duration <= DURATION_S or trial.identifier(QUIET) != QUIET_PIN:
        raise ValueError("Require the registered root, guard and bounded wait")
    scope = runpy.run_path(str(QUIET))
    devices = device_stats(Path("/proc/self/mountinfo").read_text().splitlines())
    guards = {name: scope["QuietInterval"]() for name in devices}
    proc = Path(f"/proc/{pid}")
    argv = (proc/"cmdline").read_bytes()
    if os.fsencode(DRIVER)+b"\0run\0" not in argv:
        raise ValueError("The enrolled driver is not running the pinned evaluation entry")
    children = proc/"task"/str(pid)/"children"

    def official_idle():
        if (proc/"cmdline").read_bytes() != argv:
            raise ValueError("The enrolled driver changed while waiting for its lease")
        return not children.read_text().split()

    return dict(
        sleep_until=lambda until: sleep(max(0, min(scope["POLL_S"], until-monotonic()))),
        sample=lambda: observe_quiet(scope, devices, guards), driver_idle=official_idle,
        use_lease=lease,
    )


def entry(root, pid, duration):
    machine = trial.attrs(expected_priority="idle")
    if root != ROOT:
        raise ValueError("Require the registered saved worker output")
    inputs = slot_inputs(pid, duration)
    prepare(root)
    begin, deadline = time_ns(), monotonic()+duration
    print(f"Waiting at most {duration:g}s for idle CPU2 and quiet storage", flush=True)
    def launch(fd, summary):
        return run_child(root, fd, dict(summary, driver_pid=pid), machine)
    done, counts, latest = wait_for_slot(
        deadline=deadline, cached=require_cached, launch=launch, **inputs,
    )
    pin = trial.write(root/"wait-receipt.json", dict(
        disposition="worker_finished" if done is not None else "timeout_no_worker",
        plan_sha256=PLAN_PIN, previous_watch_sha256=WATCH_PIN, previous_direct_sha256=OLD_DIRECT,
        waiter_source_sha256=trial.identifier(Path(__file__)), driver_pid=pid,
        duration_s=duration, started_unix_ns=begin, finished_unix_ns=time_ns(),
        polls=dict(counts), last_sample=latest, worker=done,
    ))
    print(pin, flush=True)
    return done


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver_pid", type=int)
    parser.add_argument("--wait-s", type=float, default=DURATION_S)
    args = parser.parse_args()
    entry(ROOT, args.driver_pid, args.wait_s)
