"""Bounded SSH saved-file benchmark on the user-selected development PLUTO+."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import time

from evaluate import ASSESS, compare_case, summarize


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for path, name in files:
            tar.add(path, arcname=name, recursive=False)
    return stream.getvalue()


def checks(files):
    return "printf '%s\\n' " + " ".join(shlex.quote(digest(p)+"  "+name) for p, name in files) + " | sha256sum -c -"


def run(args):
    if args.host != "192.168.1.15":
        raise ValueError("this experiment is bound to development host 192.168.1.15")
    args.output.mkdir(parents=True, exist_ok=False)
    bundle = args.bundle.resolve()
    manifest = json.loads((bundle / "manifest.json").read_text())
    build = json.loads((bundle / "arm/build.json").read_text())
    files = [(bundle / "arm" / name, name) for name in build["runtime_files"]]
    for p, name in files:
        if digest(p) != build["runtime_files"][name]:
            raise ValueError("binary hash changed")
    for path, expected in build["sources"].items():
        if digest(bundle / path) != expected:
            raise ValueError("scientific source changed")
    ssh = ["ssh", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes",
           "-o", "UserKnownHostsFile="+str(args.known_hosts.resolve()), "root@"+args.host]
    if args.password_file:
        ssh = ["sudo", "-n", "sshpass", "-f", str(args.password_file.resolve()), *ssh]
    else:
        ssh[1:1] = ["-o", "BatchMode=yes"]
    deadline = time.monotonic()+args.max_seconds

    def remote(command, data=None, timeout=30):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError("whole-session deadline")
        return subprocess.run([*ssh, command], input=data, capture_output=True,
                              timeout=min(timeout, remaining), check=True)

    def save(name, value):
        (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")

    metadata = remote("uname -a; cat /proc/cpuinfo; cat /proc/meminfo; cat /proc/loadavg; cat /proc/mounts; ps").stdout
    (args.output / "target-before.txt").write_bytes(metadata)
    match = re.search(rb"MemAvailable:\s+(\d+)", metadata)
    if not match or int(match[1]) < 160*1024:
        raise ValueError("less than 160 MiB available memory")
    scratch = remote("mktemp -d "+args.work_root+"/leo-static-glrt.XXXXXX").stdout.decode().strip()
    if not re.fullmatch(re.escape(args.work_root)+r"/leo-static-glrt\.[A-Za-z0-9]+", scratch):
        raise ValueError("unexpected scratch path")
    save("run-lock.json", {"host": args.host, "scratch": scratch,
         "max_seconds": args.max_seconds, "primary_rate_hz": 2500000,
         "known_hosts_sha256": digest(args.known_hosts),
         "manifest_sha256": digest(bundle / "manifest.json"),
         "build_sha256": digest(bundle / "arm/build.json"),
         "runner_sha256": digest(__file__), "assessment_sha256": digest(Path(__file__).with_name("evaluate.py")),
         "prior_assessment_sha256": digest(ASSESS), "hardware_timing": True,
         "timed_boundary": "resident saved-IQ; conversion+packing+detector; two receivers serial on one core"})
    save("manifest.json", manifest)
    save("build.json", build)
    assessments = []
    failures = []
    complete = False
    staged = set()
    registered = [n for _, n in files]
    try:
        remote("tar xf - -C "+shlex.quote(scratch), archive(files), timeout=40)
        remote("cd "+shlex.quote(scratch)+" && "+checks(files))
        for rate in (2500000, 5000000, 7500000, 10000000):
            cases = [c for c in manifest["cases"] if c["rate_hz"] == rate]
            for index, case in enumerate(cases):
                template = manifest["templates"][case["template_key"]]
                inputs = [(bundle / "data" / case["raw_file"], case["raw_file"]),
                          (bundle / "data" / template["exact"], template["exact"]),
                          (bundle / "data" / template["control"], template["control"])]
                expected = [case["raw_sha256"], template["exact_sha256"], template["control_sha256"]]
                if [digest(p) for p, _ in inputs] != expected:
                    raise ValueError("input hash changed")
                fresh = [(p, n) for p, n in inputs if n not in staged]
                remote("tar xf - -C "+shlex.quote(scratch), archive(fresh), timeout=40)
                staged.update(n for _, n in fresh)
                registered.extend(n for _, n in fresh)
                remote("cd "+shlex.quote(scratch)+" && "+checks(inputs))
                results = {}
                order = "ABCD"[index%4:]+"ABCD"[:index%4]
                for method in order:
                    command = "cd "+shlex.quote(scratch)+" && " + shlex.join([
                        "./"+method, case["raw_file"], template["exact"], template["control"],
                        str(rate), case["edge"], case["case_id"]])
                    name = case["case_id"]+"-"+method
                    command += " > "+shlex.quote(name+".json")+"; code=$?; cat "+shlex.quote(scratch+"/"+name+".json")+"; exit $code"
                    registered.append(name+".json")
                    try:
                        output = remote(command, timeout=22)
                    except subprocess.CalledProcessError as error:
                        (args.output / (name+".stderr")).write_bytes(error.stderr)
                        (args.output / (name+".json")).write_bytes(error.stdout)
                        raise
                    (args.output / (name+".json")).write_bytes(output.stdout)
                    (args.output / (name+".stderr")).write_bytes(output.stderr)
                    if b"single_core=0 " not in output.stderr:
                        raise ValueError("CPU0 affinity not attested")
                    results[method] = json.loads(output.stdout)
                remote("cd "+shlex.quote(scratch)+" && "+checks(inputs))
                assessment = compare_case(case, results)
                assessments.append(assessment)
                save("assessments.json", assessments)
                save("summary.json", summarize(assessments))
                print(case["case_id"], "PASS" if assessment["passed"] else "FAIL",
                      "A/D ms", round(assessment["methods"]["A"]["cost"]["total_cpu_ms"],2),
                      round(assessment["methods"]["D"]["cost"]["total_cpu_ms"],2), flush=True)
                if not assessment["passed"]:
                    failures.append({"case_id": case["case_id"], "rate_hz": rate,
                                     "reason": "scientific gate; remaining cases at this rate not run"})
                    save("failures.json", failures)
                    break
        remote("cd "+shlex.quote(scratch)+" && "+checks(files))
        (args.output / "target-after.txt").write_bytes(remote("cat /proc/meminfo; cat /proc/loadavg; ps").stdout)
        complete = len(assessments) == len(manifest["cases"])
    finally:
        save("completion.json", {"complete": complete, "completed_cases": len(assessments),
             "planned_cases": len(manifest["cases"]), "failures": failures,
             "elapsed_seconds": args.max_seconds-(deadline-time.monotonic())})
        if args.work_root == "/tmp":
            cleanup = "rm -f "+" ".join(shlex.quote(scratch+"/"+n) for n in registered)+" && rmdir "+shlex.quote(scratch)
        else:
            # SD inputs, binaries and raw receipts persist for repeatable development.
            cleanup = "sync"
        try:
            subprocess.run([*ssh, cleanup], capture_output=True, timeout=10, check=True)
        except (subprocess.SubprocessError, OSError) as error:
            (args.output / "cleanup-failure.txt").write_text(str(error))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.15")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--max-seconds", type=int, default=850)
    parser.add_argument("--work-root", choices=("/mnt/glrtbench", "/tmp"), default="/mnt/glrtbench")
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 850:
        parser.error("max-seconds must be 1..850 (cleanup reserves ten seconds)")
    run(args)
