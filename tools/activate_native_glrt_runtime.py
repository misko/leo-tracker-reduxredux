"""Request a tested native-watcher drain, then finish its qualified runtime handoff."""

import argparse
import json
import os
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

from stage_native_glrt_runtime import digest, verify, verify_files

SERVICE = "leo-fast-scan-analysis.service"
WATCHER_SHA256 = "c3b73217c4ae2460cfee0e999785e9ac665932cfe17e1a0cf2091709c1500651"


def read(path):
    return json.loads(path.read_text())


def property_value(name):
    return subprocess.check_output(["systemctl", "show", SERVICE, "-p", name, "--value"],
                                   text=True).strip()


def environment(pid):
    return dict(p.split("=", 1) for p in Path(f"/proc/{pid}/environ").read_text().split("\0")
                if "=" in p)


def start_ticks(pid):
    return int(Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[19])


def main_sleeping(traces, pid, source):
    mains = [t for t in traces if t["os_thread_id"] == pid and t["pid"] == pid]
    if len(mains) != 1 or not mains[0]["frames"]:
        return False
    frame = mains[0]["frames"][0]
    # This exact source revision has time.sleep(5) on line 171. The SHA gate
    # prevents this line-specific lifecycle check from applying to changed code.
    return (frame["name"] == "watch_automatic" and frame["line"] == 171
            and frame["filename"] == str(source / "src/leo/cli/fast_scan.py"))


def configuration(old, runtime, python, pin):
    lines = [s for s in old.splitlines() if s.startswith("Environment=PYTHONPATH=")]
    if len(lines) != 1 or old.count("[Service]") != 1 or "[Unit]" in old:
        raise ValueError("Unexpected native override structure")
    configured = Path(lines[0].split("=", 2)[2])
    if configured.name != "src":
        raise ValueError("Expected one native source root")
    new = old.replace(lines[0], "Environment=PYTHONPATH=" + str(runtime / "src")).rstrip()
    new = new.replace(
        "# Overlay only the orchestration files on the installed native-rate GLRT release.\n"
        "# The staged native worker preserves every other installed source byte.",
        "# Qualified native GLRT runtime with an immutable pre-start verification.")
    new += (f"\nExecStartPre={python} -B {runtime}/tools/stage_native_glrt_runtime.py verify"
            f" --root {runtime} --pin {pin}\n")
    return configured.parent, new


def request(args):
    stage, canary = read(args.stage), read(args.canary)
    root, pin = Path(stage["release"]), stage["manifest_sha256"]
    if root.parent != Path("/opt/leo-native-glrt-runtime"):
        raise ValueError("Unexpected native runtime destination")
    if not (canary["exact"] and canary["windows"] == 16 and canary["receiver_results"] == 32
            and canary["runtime_manifest_sha256"] == pin and canary["runtime_root"] == str(root)
            and canary["frozen_inputs_verified"]):
        raise ValueError("Exact installed native canary required")
    manifest = verify(root, pin)
    original = read(root / "prototype-build.json")["original_sha256"]
    pid = int(property_value("MainPID"))
    live = Path(environment(pid)["PYTHONPATH"]).parent
    verify_files(live, original)
    if digest(live / "src/leo/cli/fast_scan.py") != WATCHER_SHA256:
        raise ValueError("Live watcher differs from tested drain behavior")
    overrides = [Path(p) for p in property_value("DropInPaths").split()]
    matching = [p for p in overrides if "Environment=PYTHONPATH=" in p.read_text()]
    override = matching[-1]
    old = override.read_text()
    configured, rendered = configuration(old, root, manifest["python"], pin)
    verify_files(configured, original)
    output = args.output.resolve()
    if not output.is_relative_to("/srv/bulk/leo/research"):
        raise ValueError("Private handoff receipt directory required")
    output.mkdir(parents=True, exist_ok=False)
    (output / "previous-override.conf").write_text(old)
    (output / "next-override.conf").write_text(rendered)
    plan = dict(service=SERVICE, old_pid=pid, old_start_ticks=start_ticks(pid),
                runtime_root=str(root), manifest_sha256=pin,
                override=str(override), drain_requested=False, activated=False,
                old_override_sha256=digest(override), main_process_only=True)
    if not args.execute:
        (output / "request.json").write_text(json.dumps(plan, indent=2) + "\n")
        return plan
    handle = os.pidfd_open(pid)
    try:
        signal.pidfd_send_signal(handle, signal.SIGSTOP)
        for _ in range(100):
            states = [p.read_text().split(") ", 1)[1].split()[0]
                      for p in Path(f"/proc/{pid}/task").glob("*/stat")]
            if states and all(s == "T" for s in states):
                break
            time.sleep(.01)
        else:
            raise RuntimeError("Watcher did not stop for main-thread verification")
        sampled = subprocess.run([str(args.sampler), "dump", "--pid", str(pid), "--json",
                                  "--nonblocking", "--full-filenames"],
                                 check=True, capture_output=True, timeout=3)
        (output / "frozen-threads.json").write_bytes(sampled.stdout)
        if not main_sleeping(json.loads(sampled.stdout), pid, live):
            plan["reason"] = "Main thread outside tested sleep point; no drain signal sent"
        else:
            if (int(property_value("MainPID")) != pid
                    or digest(override) != plan["old_override_sha256"]):
                raise ValueError("Service changed during handoff preparation")
            temporary = override.with_suffix(".runtime-new")
            with temporary.open("x") as stream:
                stream.write(rendered)
            temporary.chmod(override.stat().st_mode & 0o777)
            temporary.replace(override)
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            signal.pidfd_send_signal(handle, signal.SIGINT)
            plan.update(drain_requested=True, requested_utc_ns=time.time_ns())
    finally:
        with suppress(ProcessLookupError):
            signal.pidfd_send_signal(handle, signal.SIGCONT)
        os.close(handle)
        (output / "request.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def finish(args):
    plan = read(args.request)
    if not plan["drain_requested"] or plan["service"] != SERVICE:
        raise ValueError("No native drain was requested")
    root, pin = Path(plan["runtime_root"]), plan["manifest_sha256"]
    verify(root, pin)
    if not args.output.resolve().is_relative_to("/srv/bulk/leo/research") or args.output.exists():
        raise ValueError("New private activation receipt required")
    if (Path(f"/proc/{plan['old_pid']}").exists()
            and start_ticks(plan["old_pid"]) == plan["old_start_ticks"]):
        return dict(activated=False, draining_pid=plan["old_pid"])
    if not args.execute:
        return dict(activated=False, ready_to_start=True)
    # start is idempotent if systemd already restarted it; restart could kill work.
    subprocess.run(["systemctl", "start", SERVICE], check=True)
    pid = int(property_value("MainPID"))
    if pid == plan["old_pid"] or environment(pid).get("PYTHONPATH") != str(root / "src"):
        raise RuntimeError("Replacement native watcher has another runtime")
    result = dict(activated=True, new_pid=pid, runtime_root=str(root), manifest_sha256=pin,
                  activated_utc_ns=time.time_ns(), old_pid=plan["old_pid"])
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("request")
    for name in ("stage", "canary", "sampler", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    p = commands.add_parser("finish")
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"request": request, "finish": finish}[args.command](args)))
