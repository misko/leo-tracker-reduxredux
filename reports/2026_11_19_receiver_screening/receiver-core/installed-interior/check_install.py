"""Verify published source bindings and replay the integrated standalone command."""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from tools.pipeline_eval import cavity_runtime, whole_iq
from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.qualification import cavity_pressure_probe as meter
from tools.pipeline_eval.qualification import measured_boundary_policy as parent
from tools.pipeline_eval.qualification.direct_cavity_cap import systemd_fields
from tools.pipeline_eval.scoring import ARMS, validate_result

HERE = Path(__file__).resolve().parent
PINS = {"ae62c6cd475c45788842": 12, "72aaa1db3143b2f3dc96": 13}
MEMORY, LIMIT = 512 * 2**20, 210
HASH = whole_iq._sha


def bound_requests():
    prediction = whole_iq.read(parent.REPORT / "prediction-lock.json")
    for name in ("source-lock.json", "positions.jsonl.gz", "resources.json"):
        whole_iq.checked(parent.REPORT / name, prediction["files"][name])
    selected = whole_iq.read(parent.REPORT / "source-lock.json")
    rows = {}
    for ident, cpu in PINS.items():
        expected = selected["offers"][ident]
        path = whole_iq.checked(parent.WORK / ident / "request.json", expected["request_sha256"])
        prior = whole_iq.read(path)
        case, original = whole_iq.binding(expected["recording"])
        if (
            prior["archive"] != original["job"]["tle_root"]
            or prior["config"] != original["job"]["track_config"]
            or prior["session"] != case["session_id"]
            or prior["native_sha256"] != case["native"]["sha256"]
            or prior["tile"] != expected["tile"]["center"]
            or prior["screen"] != prior["tile"]
            or prior["width_km"] != expected["tile"]["width_km"]
            or prior["native_sha256"] != expected["native_sha256"]
            or original["causal_snapshots"] != expected["causal_snapshots"]
        ):
            raise ValueError("integrated replay differs from sealed recorded factors or offer")
        whole_iq.checked(Path(prior["native"]), expected["native_sha256"])
        for mode in ("on", "off"):
            name = f"{ident}-guard-{mode}.json"
            whole_iq.checked(parent.REPORT / name, prediction["files"][name])
        rows[ident] = dict(offer=expected, command=prior, cpu=cpu)
    return rows, selected["installed_files"]


def lock(work):
    installed = work / "interior"
    archive, baseline = bound_requests()
    identity = whole_iq.receiver_identity(installed)
    changed = {"__main__.py", "tools/__init__.py", "native/manifest.json"}
    if (
        set(identity) != set(baseline) | {cavity_runtime.INTERIOR_RULE}
        or {k for k in baseline if baseline[k] != identity[k]} != changed
    ):
        raise ValueError("integrated receiver changed original scientific source or binaries")
    if whole_iq.native_sources(installed) != whole_iq.native_sources(parent.INSTALL):
        raise ValueError("integrated receiver changed original compiler inputs")
    save_json(
        work / "plan.json",
        dict(
            offers=archive,
            files=identity,
            expected_changed=sorted(changed),
            native_sources=whole_iq.native_sources(installed),
            measured_parent_sha256=HASH(parent.REPORT / "prediction-lock.json"),
            protocol_sha256=HASH(HERE / "PROTOCOL.md"),
            harness_sha256=HASH(Path(__file__)),
            builder_sha256=HASH(Path(cavity_runtime.__file__)),
            memory_bytes=MEMORY,
            swap_max=0,
            limit_s=LIMIT,
        ),
    )


def argv(installed, row):
    r = row["command"]
    return [
        sys.executable,
        "-IB",
        str(installed),
        "--native",
        r["native"],
        "--native-sha256",
        r["native_sha256"],
        "--session",
        r["session"],
        "--track-config",
        r["config"]["path"],
        "--config-sha256",
        r["config"]["sha256"],
        "--archive",
        r["archive"],
        "--tile",
        *map(str, r["tile"]),
        "--screen-center",
        *map(str, r["screen"]),
        "--width-km",
        str(r["width_km"]),
    ]


def run(work, ident):
    plan_file, release = work / "plan.json", work / "interior"
    plan = whole_iq.read(plan_file)
    row, cpu = plan["offers"][ident], PINS[ident]
    if (
        os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
        or row != bound_requests()[0][ident]
        or whole_iq.receiver_identity(release) != plan["files"]
        or whole_iq.native_sources(release) != plan["native_sources"]
        or HASH(Path(__file__)) != plan["harness_sha256"]
    ):
        raise ValueError("integrated replay left its declared source, input or processor")
    target = work / ident
    target.mkdir(exist_ok=False)
    unit = "leo-installed-interior-" + uuid4().hex[:10]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={target}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=MemoryAccounting=yes",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--setenv=TMPDIR={target}",
        "taskset",
        "-c",
        str(cpu),
        *argv(release, row),
    ]
    stdout, stderr = target / "position.json", target / "service.log"
    began, group, samples, pids = monotonic(), None, [], {}
    with stdout.open("xb") as out, stderr.open("xb") as err:
        child = subprocess.Popen(command, stdout=out, stderr=err)
        while child.poll() is None and monotonic() - began < LIMIT + 7:
            group = group or systemd_fields(unit).get("ControlGroup")
            if group:
                root = Path("/sys/fs/cgroup") / group.lstrip("/")
                try:
                    samples.append(meter.kernel(root))
                    for pid in map(int, (root / "cgroup.procs").read_text().split()):
                        sub = Path("/proc") / str(pid)
                        words = (sub / "cmdline").read_bytes().split(b"\0")
                        if words[1:3] == [b"-IB", os.fsencode(release)]:
                            pids[pid] = sorted(os.sched_getaffinity(pid))
                except (FileNotFoundError, ProcessLookupError):
                    pass
            sleep(0.25)
        if child.poll() is None:
            subprocess.run(["systemctl", "--user", "stop", unit], timeout=4, check=False)
        child.wait(timeout=5)
    wall, status = monotonic() - began, systemd_fields(unit)
    end = re.search(r"Finished with result: (\S+)", stderr.read_text(errors="replace"))
    service = end[1] if end else status["Result"]
    if not samples or any(
        s["memory.max"] != MEMORY or s["memory.swap.max"] or s["memory.swap.current"]
        for s in samples
    ):
        raise ValueError("physical memory/swap resource evidence is missing or inconsistent")
    if service == "success" and child.returncode == 0:
        if list(pids.values()) != [[cpu]]:
            raise ValueError("expected one direct standalone interpreter on the registered CPU")
        prediction = whole_iq.read(stdout)
    else:
        prediction = dict(
            status="timed_out" if service == "timeout" else "failed",
            reason=f"standalone service {service}",
            boundary="Stored native factors through the installed interior publication rule",
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        )
    validate_result(prediction)
    save_json(
        target / "receipt.json",
        dict(
            id=ident,
            cpu=cpu,
            pids=pids,
            wall_s=wall,
            returncode=child.returncode,
            result=prediction,
            service_result=service,
            kernel=status,
            samples=samples,
            plan_sha256=HASH(plan_file),
            output_sha256=HASH(stdout),
            log_sha256=HASH(stderr),
        ),
    )
    print(ident, service, prediction["status"], round(wall, 2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("operation", choices=("lock", "run"))
    parser.add_argument("case", nargs="?", choices=PINS)
    p = parser.parse_args()
    folder = local_output(p.work)
    if p.operation == "lock":
        lock(folder)
    else:
        run(folder, p.case)
