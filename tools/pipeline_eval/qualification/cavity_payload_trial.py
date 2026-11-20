"""Paired capped executions of the complete and reduced standalone source packages."""

import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter, time_ns
from uuid import uuid4

from . import cavity_payload
from . import direct_cavity_trial as direct
from . import direct_lifetime_trial as lifetime

REPORT = direct.common.SCREEN / "next/cavity-payload"
PARENT = REPORT.with_name("direct-lifetime")
CASES = {
    "ordinary-DS26-0036": (0, ("full", "small")),
    "ordinary-DS29-0082": (1, ("small", "full")),
    "capture-era-DS26-0112": (2, ("small", "full")),
    "capture-era-DS29-0127": (3, ("full", "small")),
}
THREADS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "OPENBLAS_NUM_THREADS")


def stage(work):
    work.mkdir(exist_ok=False)
    receipt = direct.common.seal(
        PARENT, "receipt.json", ("bundle.json", "compact-cavity-source.tar.gz")
    )
    manifest = direct.common.read(PARENT / "bundle.json")
    files = cavity_payload.read_bundle(PARENT / "compact-cavity-source.tar.gz", manifest["files"])
    small = cavity_payload.source_closure(files)
    packages = {}
    for label, members in (("full", files), ("small", small)):
        dest = work / label
        for name, data in members.items():
            target = dest / name
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes(data)
        blob = cavity_payload.packed(members)
        (work / (label + ".tar.gz")).write_bytes(blob)
        script = (
            "import sys;sys.path.insert(0,sys.argv[1]);"
            "from leo.analysis.localization_v4.backend import build_native;"
            "from tools.pipeline_eval.variants.orbit_projector import compile_kernel;"
            "build_native('native');compile_kernel('projector.so')"
        )
        subprocess.run(
            [str(direct.v5_lean.PYTHON), "-IB", "-c", script, str(dest)],
            cwd=dest,
            env=dict(os.environ, TMPDIR=str(work), **dict.fromkeys(THREADS, "1")),
            check=True,
            timeout=40,
        )
        binaries = {
            f: direct.common.sha(dest / f) for f in ("native/native_bound.so", "projector.so")
        }
        if binaries["native/native_bound.so"] != manifest["binary"]:
            raise ValueError("native bound differs from the published direct lifetime receiver")
        packages[label] = dict(
            files={name: cavity_payload.digest(data) for name, data in members.items()},
            count=len(members),
            raw_bytes=sum(map(len, members.values())),
            python_lines=sum(len(v.splitlines()) for k, v in members.items() if k.endswith(".py")),
            archive_bytes=len(blob),
            archive_sha256=cavity_payload.digest(blob),
            binaries=binaries,
            native_manifest_sha256=direct.common.sha(dest / "native/manifest.json"),
        )
    if packages["small"]["binaries"] != packages["full"]["binaries"]:
        raise ValueError("different numerical binaries")
    protocol = REPORT / "PROTOCOL.md"
    return dict(
        packages=packages,
        frozen_ns=time_ns(),
        cases=CASES,
        bindings={key: direct.input_case(key)[2] for key in CASES},
        parent_sources=receipt["files"]["compact-cavity-source.tar.gz"],
        code={
            p.name: direct.common.sha(p)
            for p in (
                Path(__file__),
                Path(cavity_payload.__file__),
                Path(lifetime.__file__),
                protocol,
            )
        },
    )


def run_case(work, plan, case_key):
    cpu, order = CASES[case_key]
    case, request, binding = direct.input_case(case_key)
    if binding != plan["bindings"][case_key]:
        raise ValueError("input binding changed")
    for variant in order:
        stage_root = work / variant
        package = plan["packages"][variant]
        verify = (
            package["files"]
            | package["binaries"]
            | {"native/manifest.json": package["native_manifest_sha256"]}
        )
        if any(direct.common.sha(stage_root / f) != d for f, d in verify.items()):
            raise ValueError("source or numerical library changed")
        out = work / "runs" / case_key / variant
        out.mkdir(exist_ok=False, parents=True)
        cli = direct.direct_command(case, request["job"], stage_root, stage_root / "projector.so")
        unit = "leo-cavity-dist-" + uuid4().hex[:12]
        # -I removes the checkout and PYTHONPATH. Inspect module origins after the
        # solve as a second check against an editable site-package import.
        worker = (
            "import sys,runpy,json; from pathlib import Path;"
            "root=Path(sys.argv[2]);sys.path.insert(0,str(root));"
            "observer=runpy.run_path(sys.argv[1]);"
            "observer['observe'](sys.argv[3],int(sys.argv[4]),root,sys.argv[5:]);"
            "sources={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() "
            "if n.split('.')[0] in ('leo','tools') and getattr(m,'__file__',None)};"
            "print('origins '+json.dumps(sources,sort_keys=True),file=sys.stderr);"
            "assert all(Path(p).is_relative_to(root) for p in sources.values())"
        )
        command = [
            "systemd-run",
            "--user",
            "--pipe",
            "--wait",
            f"--unit={unit}",
            f"--working-directory={stage_root}",
            f"--property=MemoryMax={lifetime.MEMORY}",
            "--property=MemorySwapMax=0",
            f"--property=RuntimeMaxSec={lifetime.LIMIT}s",
            "--property=Nice=10",
            "--property=KillMode=control-group",
            f"--setenv=TMPDIR={lifetime.TMP}",
            *(f"--setenv={v}=1" for v in THREADS),
            "/usr/bin/taskset",
            "-c",
            str(cpu),
            cli[0],
            "-IB",
            "-c",
            worker,
            str(Path(lifetime.__file__).resolve()),
            str(stage_root),
            unit,
            str(cpu),
            *cli[4:],
        ]
        started = perf_counter()
        exit_code, launch_failure = supervise(command, unit, out)
        wall = perf_counter() - started
        result, values, exit_code = service_result(out, exit_code, launch_failure)
        evidence = dict(
            binding,
            method="v5_cavity_payload_" + variant,
            result=result,
            cpu=cpu,
            wall_s=wall,
            exit_code=exit_code,
            measurements=values,
        )
        direct.save_json(out / "attempt.json", evidence)
        print(case_key, variant, result["status"], round(wall, 2), flush=True)


def supervise(command, unit, out):
    with (out / "stdout").open("xb") as stdout, (out / "stderr").open("xb") as stderr:
        try:
            proc = subprocess.run(
                command, stdout=stdout, stderr=stderr, timeout=lifetime.LIMIT + 12
            )
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(["systemctl", "--user", "stop", unit], timeout=10, check=True)
            except (OSError, subprocess.SubprocessError) as error:
                return 124, f"service supervisor timeout, stop request failed: {error}"
            return 124, "service supervisor timeout"
        except OSError as error:
            return 127, f"service launch failed: {error}"
    return proc.returncode, None


def service_result(out, exit_code, failure):
    values = {}
    lines = (out / "stderr").read_text(errors="replace").splitlines()
    for line in lines:
        label, _, data = line.partition(" ")
        if label in ("finish", "proof", "origins"):
            try:
                values[label] = json.loads(data)
            except ValueError:
                failure = failure or f"incomplete service record: {label}"
    if not exit_code and not failure:
        try:
            if not all(values.get(k) for k in ("origins", "finish", "proof")):
                raise ValueError("missing process origin, finish, or cap proof")
            result = json.loads((out / "stdout").read_bytes())
            direct.validate_result(result)
            return result, values, exit_code
        except (KeyError, TypeError, ValueError) as error:
            failure = f"unverified service result: {error}"
    reason = failure or next(
        (s for s in lines if s.startswith("Failed with result")), "service failed"
    )
    status = "timed_out" if "timeout" in reason else "failed"
    return direct.v5_lean._no_fix(reason, status=status), values, exit_code or 1


def scientific_result(result):
    return (
        result.get("status"),
        result.get("reason"),
        result["arms"],
        {k: v for k, v in result["metrics"].items() if k != "stage_s"},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    work = direct.local_output(args.work)
    if args.action == "stage":
        direct.save_json(work / "plan.json", stage(work))
    else:
        plan = direct.common.read(work / "plan.json")
        for module in (
            Path(__file__),
            Path(lifetime.__file__),
            Path(cavity_payload.__file__),
            REPORT / "PROTOCOL.md",
        ):
            if plan["code"][module.name] != direct.common.sha(module):
                raise ValueError(f"qualification source changed: {module.name}")
        with ThreadPoolExecutor(max_workers=len(CASES)) as pool:
            list(pool.map(lambda case: run_case(work, plan, case), CASES))
