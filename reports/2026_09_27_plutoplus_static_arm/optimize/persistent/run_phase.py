#!/usr/bin/env python3
"""Run one bounded phase with an isolated optimized persistent worker."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time


HERE = Path(__file__).resolve().parent
OPTIMIZE = HERE.parent
CONCURRENT = OPTIMIZE.parent / "concurrent"
SSH = [
    "sudo", "-n", "sshpass", "-f",
    "/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/artifacts/native-lnb-20-20260910/ssh-password",
    "ssh", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5",
    "-o", "StrictHostKeyChecking=yes", "-o",
    "UserKnownHostsFile=/tmp/leo-static-arm-access/known_hosts",
    "root@192.168.1.15",
]
TARGET_ROOT = "/mnt/glrtbench/leo-static-glrt.4jwvdm"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def remote(command, timeout=10, input_data=None):
    return subprocess.check_output([*SSH, command], timeout=timeout, input=input_data)


def validate(args):
    if len(args.name) > 48 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.name):
        raise ValueError("phase name")
    if not re.fullmatch(r"[a-z0-9_]+", args.candidate):
        raise ValueError("candidate")
    if not 1 <= args.jobs <= 600 or not 120 <= args.period <= 1000:
        raise ValueError("jobs/period")
    if args.jobs * args.period > 90_000:
        raise ValueError("phase duration")
    if not 5 <= args.seconds <= 120 or not 5 <= args.capture_seconds <= 60:
        raise ValueError("monitor/capture duration")
    if args.capture_rate != 2_500_000:
        raise ValueError("optimized combined cohort is 2.5 MS/s only")
    flavor = "cadence" if args.recorded_arrivals else "paced"
    arrival_path = CONCURRENT / "arrival-offsets.txt"
    if args.recorded_arrivals:
        arrivals = [float(line) for line in arrival_path.read_text().splitlines()]
        if args.jobs > len(arrivals) or not arrivals or arrivals[0] != 0 or \
                any(right < left for left, right in zip(arrivals, arrivals[1:])):
            raise ValueError("recorded arrival schedule")
    build = HERE / "build" / f"{args.candidate}-{flavor}-arm"
    receipt_path = build.with_suffix(".build.json")
    receipt = json.loads(receipt_path.read_text())
    if receipt["candidate"] != args.candidate or receipt.get("flavor", "paced") != flavor or \
            sha(build) != receipt["binary_sha256"]:
        raise ValueError("persistent worker receipt mismatch")
    qualification = json.loads(Path(receipt["qualification"]).read_text())
    if not qualification.get("complete") or not qualification.get("passed"):
        raise ValueError("candidate qualification failed")
    return build, receipt_path, receipt


def write_state(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(path)


def with_optional_irq1(enabled, evidence, action, remote_call=remote):
    if not enabled:
        return action()
    line = remote_call("sed -n '/eth0/p' /proc/interrupts").decode()
    rows = [row for row in line.splitlines() if row.strip()]
    if len(rows) != 1:
        raise RuntimeError("eth0 IRQ identity is ambiguous")
    match = re.match(r"\s*([0-9]+):", rows[0])
    if not match:
        raise RuntimeError("eth0 IRQ line is malformed")
    irq = int(match.group(1))
    original = remote_call(f"cat /proc/irq/{irq}/smp_affinity").decode().strip()
    try:
        original_value = int(original.replace(",", ""), 16)
    except ValueError as error:
        raise RuntimeError("unexpected original IRQ affinity") from error
    state = {"irq": irq, "device": "eth0", "original_mask": original,
             "original_interrupts": rows[0], "restoration_attempted": False}
    write_state(evidence, state)
    phase_error = None
    result = None
    try:
        remote_call(f"echo 2 > /proc/irq/{irq}/smp_affinity")
        state["during_mask"] = remote_call(
            f"cat /proc/irq/{irq}/smp_affinity").decode().strip()
        state["during_effective_cpu"] = remote_call(
            f"cat /proc/irq/{irq}/effective_affinity_list").decode().strip()
        if int(state["during_mask"].replace(",", ""), 16) != 2 or \
                state["during_effective_cpu"] != "1":
            raise RuntimeError("IRQ CPU1 pin failed")
        write_state(evidence, state)
        result = action()
    except BaseException as error:
        phase_error = error
        state["phase_error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        state["restoration_attempted"] = True
        try:
            remote_call(f"echo {shlex.quote(original)} > /proc/irq/{irq}/smp_affinity")
            restored = remote_call(f"cat /proc/irq/{irq}/smp_affinity").decode().strip()
            state["restored_mask"] = restored
            state["restored_effective_cpu"] = remote_call(
                f"cat /proc/irq/{irq}/effective_affinity_list").decode().strip()
            state["restored"] = int(restored.replace(",", ""), 16) == original_value
            if not state["restored"]:
                raise RuntimeError("IRQ restoration verification failed")
        except BaseException as restore_error:
            state["restoration_error"] = f"{type(restore_error).__name__}: {restore_error}"
            state["restored"] = False
            write_state(evidence, state)
            raise RuntimeError("IRQ restoration failed; inspect irq-affinity.json") from restore_error
        write_state(evidence, state)
    return result


def stage_worker(binary, digest, remote_call=remote):
    target_name = f"opt-worker-{digest[:16]}"
    target = TARGET_ROOT + "/" + target_name
    command = (
        "set -eu; target=" + shlex.quote(target) + "; tmp=${target}.tmp.$$; "
        "if test -e \"$target\"; then sha256sum \"$target\"; "
        "else trap 'rm -f \"$tmp\"' EXIT; umask 077; cat > \"$tmp\"; "
        "chmod 700 \"$tmp\"; mv \"$tmp\" \"$target\"; trap - EXIT; "
        "sha256sum \"$target\"; fi"
    )
    observed = remote_call(command, timeout=30, input_data=binary.read_bytes()).decode().split()[0]
    if observed != digest:
        raise RuntimeError("staged worker hash mismatch")
    return target_name


def execute(args, full_name, output, build, receipt_path, receipt):
    digest = receipt["binary_sha256"]
    executable = stage_worker(build, digest)
    if args.recorded_arrivals:
        arrival_digest = sha(CONCURRENT / "arrival-offsets.txt")
        observed = remote("sha256sum " + shlex.quote(
            TARGET_ROOT + "/arrival-offsets.txt")).decode().split()[0]
        if observed != arrival_digest:
            raise RuntimeError("target arrival-offsets.txt hash mismatch")
    target_dir = TARGET_ROOT + "/optimize-" + full_name
    before = time.monotonic_ns()
    uptime = remote("cat /proc/uptime").decode()
    after = time.monotonic_ns()
    (output / "clock.json").write_text(json.dumps(
        {"host_before_ns": before, "host_after_ns": after, "target_uptime": uptime}) + "\n")
    snapshot = "cat /proc/interrupts; cat /proc/softirqs; cat /proc/net/dev; cat /proc/diskstats; cat /proc/meminfo; ps"
    (output / "target-before.txt").write_bytes(remote(snapshot))
    arrival_argument = " arrival-offsets.txt" if args.recorded_arrivals else ""
    command = (
        f"mkdir {shlex.quote(target_dir)} && cd {shlex.quote(TARGET_ROOT)} && "
        f"(./{shlex.quote(executable)} cases-2500000.txt 2500000 {args.jobs} "
        f"{args.period} {args.core} {args.rx}{arrival_argument} > {shlex.quote(target_dir)}/glrt.jsonl "
        f"2> {shlex.quote(target_dir)}/glrt.stderr & gpid=$!; "
        f"echo $gpid > {shlex.quote(target_dir)}/glrt.pid; "
        f"./monitor-arm {args.seconds} 220 $gpid > {shlex.quote(target_dir)}/cpu.jsonl; "
        f"wait $gpid; echo $? > {shlex.quote(target_dir)}/glrt.exit)"
    )
    source_hashes = {
        "worker": digest,
        "worker_build_receipt": sha(receipt_path),
        "runner": sha(__file__),
        "monitor.c": sha(CONCURRENT / "monitor.c"),
        "monitor-arm": sha(CONCURRENT / "monitor-arm"),
        "capture.py": sha(CONCURRENT / "capture.py"),
        "cases-2500000.txt": sha(CONCURRENT / "cases-2500000.txt"),
    }
    if args.recorded_arrivals:
        source_hashes["arrival-offsets.txt"] = sha(CONCURRENT / "arrival-offsets.txt")
    (output / "run.json").write_text(json.dumps({
        **vars(args), "phase_name": full_name, "target_directory": target_dir,
        "target_executable": executable, "command": command,
        "source_hashes": source_hashes,
    }, indent=2) + "\n")
    phase_error = None
    capture = None
    with (output / "remote.stdout").open("wb") as stdout, \
            (output / "remote.stderr").open("wb") as stderr:
        work = subprocess.Popen([*SSH, command], stdout=stdout, stderr=stderr)
        try:
            time.sleep(3)
            for _ in range(15):
                first = remote("head -n 1 " + shlex.quote(target_dir + "/glrt.jsonl")).strip()
                if first:
                    ready = json.loads(first)
                    if ready.get("type") != "ready":
                        raise RuntimeError("no GLRT ready marker")
                    (output / "ready.json").write_text(json.dumps(ready) + "\n")
                    break
                time.sleep(1)
            else:
                raise RuntimeError("GLRT did not become ready")
            if args.capture:
                environment = {**os.environ,
                    "PYTHONPATH": "/opt/leo-v058-adaptive/1e7bebed663bc2178a1b91af5b98eb55bc97dc84/src",
                    "LEO_BENCH_PHASE": full_name}
                capture_command = [
                    "/home/mouse9911/gits/pluto-plus-utils-feature-103/.venv/bin/python",
                    str(CONCURRENT / "capture.py"), "--seconds", str(args.capture_seconds),
                    "--rate", str(args.capture_rate), "--output", str(output / "capture")]
                with (output / "capture.stdout").open("wb") as capture_stdout, \
                        (output / "capture.stderr").open("wb") as capture_stderr:
                    capture = subprocess.Popen(capture_command, env=environment,
                        stdout=capture_stdout, stderr=capture_stderr)
                    try:
                        capture.wait(timeout=100)
                    except subprocess.TimeoutExpired:
                        capture.send_signal(signal.SIGINT)
                        capture.wait(timeout=30)
                (output / "capture.exit").write_text(str(capture.returncode) + "\n")
        except BaseException as error:
            phase_error = error
        finally:
            try:
                work.wait(timeout=130)
            except subprocess.TimeoutExpired:
                work.kill()
                work.wait(timeout=10)
                if phase_error is None:
                    phase_error = TimeoutError("remote phase exceeded bound")
    (output / "remote.exit").write_text(str(work.returncode) + "\n")
    for name in ("cpu.jsonl", "glrt.jsonl", "glrt.stderr", "glrt.exit", "glrt.pid"):
        (output / name).write_bytes(remote("cat " + shlex.quote(target_dir + "/" + name)))
    before = time.monotonic_ns()
    uptime = remote("cat /proc/uptime").decode()
    after = time.monotonic_ns()
    (output / "clock-after.json").write_text(json.dumps(
        {"host_before_ns": before, "host_after_ns": after, "target_uptime": uptime}) + "\n")
    (output / "target-after.txt").write_bytes(remote(snapshot))
    errors = []
    if phase_error:
        errors.append(str(phase_error))
    if work.returncode:
        errors.append("remote exit")
    if int((output / "glrt.exit").read_text()):
        errors.append("GLRT exit")
    rows = [json.loads(line) for line in (output / "glrt.jsonl").read_text().splitlines()]
    if not rows or rows[-1].get("type") != "complete":
        errors.append("GLRT incomplete")
    if sum(row.get("type") == "visit" for row in rows) != args.jobs:
        errors.append("GLRT job count")
    if args.capture:
        capture_receipt = output / "capture/receipt.json"
        if capture is None or capture.returncode or not capture_receipt.exists():
            errors.append("capture incomplete")
        else:
            captured = json.loads(capture_receipt.read_text())
            restoration, terminal = captured["restoration"], captured["terminal"]
            if terminal["state"] != 1 or terminal["error"] or any(
                    terminal[key] for key in ("skipped", "invalid", "cancelled")):
                errors.append("capture integrity")
            if restoration["expected"] != restoration["observed"] or \
                    restoration["expected_kernel_buffers"] != restoration["observed_kernel_buffers"] or \
                    not restoration["fastlock_inactive"]:
                errors.append("capture restoration")
    (output / "validity.json").write_text(json.dumps(
        {"passed": not errors, "errors": errors}, indent=2) + "\n")
    if errors:
        raise RuntimeError(errors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="suffix; output phase is opt-CANDIDATE-NAME")
    parser.add_argument("--candidate", default="rankconversion")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--irq1", action="store_true")
    parser.add_argument("--recorded-arrivals", action="store_true")
    parser.add_argument("--core", type=int, choices=(0, 1), default=0)
    parser.add_argument("--rx", type=int, choices=(1, 2), default=2)
    parser.add_argument("--jobs", type=int, default=500)
    parser.add_argument("--period", type=int, default=120)
    parser.add_argument("--seconds", type=int, default=75)
    parser.add_argument("--capture-seconds", type=int, default=45)
    parser.add_argument("--capture-rate", type=int, default=2_500_000)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    build, receipt_path, receipt = validate(args)
    cadence = "-recorded" if args.recorded_arrivals else ""
    full_name = f"opt-{args.candidate.replace('_', '-')}{cadence}-{args.name}"
    output = HERE / "runs" / full_name
    if args.validate_only:
        result = {"phase_name": full_name, "binary": str(build),
                  "binary_sha256": receipt["binary_sha256"]}
        if args.recorded_arrivals:
            result["arrival_offsets_sha256"] = sha(CONCURRENT / "arrival-offsets.txt")
            result["arrival_offsets_count"] = len(
                (CONCURRENT / "arrival-offsets.txt").read_text().splitlines())
        print(json.dumps(result))
        return
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "irq-affinity.json"
    with_optional_irq1(args.irq1, evidence,
        lambda: execute(args, full_name, output, build, receipt_path, receipt))
    print("finished", full_name, flush=True)


if __name__ == "__main__":
    main()
