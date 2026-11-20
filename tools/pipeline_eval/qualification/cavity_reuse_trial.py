"""Build exact reuse overlays and run matched 512 MiB standalone pairs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, time_ns
from uuid import uuid4

from ..__main__ import local_output, save_json
from ..scoring import ARMS
from ..variants import cavity_reuse_columns as private
from . import cavity_payload_trial as apparatus
from . import cavity_reuse_observe as observer
from . import direct_cavity_trial as direct
from .full_receiver_comparison import read, require_fields, seal, sha

REPORT = direct.common.SCREEN / "detector-origins/compact-reuse"
CASES = {
    "DS26-0036": (16, ("stock", "columns", "checksum")),
    "DS29-0082": (17, ("checksum", "columns", "stock")),
}
HOLDOUT = {
    "DS26-0112": (16, ("stock", "columns")),
    "DS29-0127": (17, ("columns", "stock")),
}
LIMIT = 155
MODES = ("stock", "columns", "checksum")
LIBRARIES = ("native/native_bound.so", "projector.so")
PREFIX = "tools/pipeline_eval/variants/"
ENTRY = PREFIX + "v5_direct_cavity.py"
CORE = PREFIX + "v5_core.py"
OVERLAY = PREFIX + "cavity_reuse_columns.py"
METHODS = dict(
    stock="v5_direct_lifetime", columns="v5_cavity_reuse", checksum="v5_cavity_tle_reuse"
)


def splice(data, anchor, replacement):
    if data.count(anchor) != 1:
        raise ValueError("the installed release does not contain the exact overlay anchor")
    return data.replace(anchor, replacement)


def overlay(root, mode):
    from ..cavity_runtime import RELEASE

    manifest = read(RELEASE / "package.json")
    modifications = {}
    for file in (ENTRY, CORE):
        path = root / file
        if sha(path) != manifest["files"][file]:
            raise ValueError(f"overlay expected the published source at {file}")
    entry = (root / ENTRY).read_text()
    if mode == "columns":
        core = (root / CORE).read_text()
        core = splice(
            core,
            "    with projection_columns():\n        ranked = ranked_initial_nodes(scan)[:3]",
            "    from .cavity_reuse_columns import shared_initial_columns\n\n"
            "    with projection_columns(), shared_initial_columns(scan.geometry):\n"
            "        ranked = ranked_initial_nodes(scan)[:3]",
        )
        modifications[CORE] = core
    if mode == "checksum":
        entry = splice(
            entry,
            "        prepare_native_scan(\n",
            "        prepare_with_checksum_reuse(\n            prepare_native_scan,\n",
        )
        entry = splice(
            entry,
            "    from leo.application.localization_v3_engine import _prepared_values\n",
            "    from leo.application.localization_v3_engine import _prepared_values\n"
            "    from .cavity_reuse_columns import prepare_with_checksum_reuse\n",
        )
    modifications[ENTRY] = splice(
        entry,
        '    result["metrics"]["compact_projections"] = projector.calls\n',
        "    from .cavity_reuse_columns import receipt\n"
        '    result["metrics"]["compact_projections"] = projector.calls\n'
        '    result["metrics"]["reuse_trace"] = receipt()\n',
    )
    modifications[OVERLAY] = Path(private.__file__).read_text()
    for file, value in modifications.items():
        (root / file).write_text(value)
    return {file: sha(root / file) for file in sorted(modifications)}


def install(root, mode):
    from ..cavity_runtime import install as build

    build(root)
    return overlay(root, mode) if mode != "stock" else {}


def qualify_input(ident, cohort):
    case, request, binding = direct.input_case(cohort + "-" + ident)
    if request["job"]["evaluation_reference"] is not None:
        raise ValueError("evaluation truth is outside the standalone classifier")
    return case, request["job"], binding


def lock(work, holdout):
    from ..cavity_runtime import RELEASE

    parent = seal(RELEASE, "prediction-lock.json", ("receiver-source.tar.gz", "package.json"))
    package = read(RELEASE / "package.json")
    cohort, schedule = ("capture-era", HOLDOUT) if holdout else ("ordinary", CASES)
    modes = MODES[:2] if holdout else MODES
    protocol = REPORT / ("holdout/PROTOCOL.md" if holdout else "PROTOCOL.md")
    if holdout:
        historical = seal(RELEASE, "prediction-lock.json", ("source-lock.json",))
        historical_plan = read(RELEASE / "source-lock.json")
        reserve = {
            key.removeprefix("capture-era-")
            for key in historical_plan["cases"]
            if key.startswith("capture-era-")
        }
        if set(HOLDOUT) != reserve:
            raise ValueError("holdout roster differs from the previously sealed release reserve")
    work.mkdir(exist_ok=False)
    releases = {}
    for mode in modes:
        root = work / mode
        updates = install(root, mode)
        files = package["files"] | updates
        observed = {f: sha(root / f) for f in LIBRARIES}
        require_fields(observed, package["binaries"])
        releases[mode] = dict(
            source_count=len(files),
            files=files,
            overlay=updates,
            libraries=observed,
            manifest_sha256=sha(root / "native/manifest.json"),
            public_entry_sha256=sha(root / "__main__.py"),
            package_init_sha256=sha(root / "tools/__init__.py"),
        )
    stage_source = (
        Path(__file__),
        Path(private.__file__),
        Path(observer.__file__),
        protocol,
    )
    plan = dict(
        cases=list(schedule),
        bindings={i: qualify_input(i, cohort)[2] for i in schedule},
        schedule=schedule,
        releases=releases,
        frozen_ns=time_ns(),
        baseline_receipt_sha256=sha(RELEASE / "prediction-lock.json"),
        baseline_archive_sha256=parent["files"]["receiver-source.tar.gz"],
        code={p.name: sha(p) for p in stage_source},
        memory_bytes=apparatus.lifetime.MEMORY,
        swap_bytes=0,
        limit_s=LIMIT,
        nice=10,
    )
    if holdout:
        plan.update(cohort=cohort, prior_roster_lock_sha256=historical["files"]["source-lock.json"])
    save_json(work / "plan.json", plan)


def flags_for(case, job, path):
    args = direct.direct_command(case, job, path, path / "projector.so")[4:]
    for name in ("--native-backend", "--library"):
        index = args.index(name)
        del args[index : index + 2]
    return args


def run(work, plan, ident):
    cpu, order = plan["schedule"][ident]
    case, job, binding = qualify_input(ident, plan.get("cohort", "ordinary"))
    require_fields(binding, plan["bindings"][ident])
    for mode in order:
        path = work / mode
        expected = plan["releases"][mode]
        files = (
            expected["files"]
            | expected["libraries"]
            | {
                "native/manifest.json": expected["manifest_sha256"],
                "__main__.py": expected["public_entry_sha256"],
                "tools/__init__.py": expected["package_init_sha256"],
            }
        )
        if any(sha(path / f) != value for f, value in files.items()):
            raise ValueError(f"{mode} standalone source or binaries changed")
        output = work / "runs" / ident / mode
        output.mkdir(parents=True, exist_ok=False)
        unit = f"leo-reuse-{ident.lower()}-{uuid4().hex[:8]}"
        cmd = [
            "systemd-run",
            "--user",
            "--wait",
            "--pipe",
            f"--unit={unit}",
            f"--working-directory={path}",
            f"--setenv=TMPDIR={work}",
            "--property=MemoryMax=536870912",
            "--property=MemorySwapMax=0",
            f"--property=RuntimeMaxSec={LIMIT}s",
            "--property=Nice=10",
            "--property=KillMode=control-group",
            *(f"--setenv={v}=1" for v in apparatus.THREADS),
            "/usr/bin/taskset",
            "-c",
            str(cpu),
            str(direct.v5_lean.PYTHON),
            "-IB",
            str(Path(observer.__file__)),
            unit,
            str(cpu),
            str(path),
            *flags_for(case, job, path),
        ]
        begin = monotonic()
        code, failure = apparatus.supervise(cmd, unit, output)
        wall = monotonic() - begin
        result, measurements, code = apparatus.service_result(output, code, failure)
        result.setdefault("arms", {arm: {"latlon": None} for arm in ARMS})
        save_json(
            output / "attempt.json",
            dict(
                binding,
                id=ident,
                mode=mode,
                method=METHODS[mode],
                cpu=cpu,
                wall_s=wall,
                result=result,
                measurements=measurements,
                exit_code=code,
                unit=unit,
                worker_log_sha256=sha(output / "stderr"),
                source_lock_sha256=sha(work / "plan.json"),
            ),
        )
        print(ident, mode, result["status"], round(wall, 3), result.get("reason", ""), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run", "install"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--profile", choices=MODES, default="columns")
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    if args.action == "install":
        install(args.work, args.profile)
    elif args.action == "seal":
        lock(args.work, args.holdout)
    else:
        plan = read(args.work / "plan.json")
        for name, path in (
            (Path(__file__).name, Path(__file__)),
            (Path(observer.__file__).name, Path(observer.__file__)),
            (Path(private.__file__).name, Path(private.__file__)),
        ):
            if sha(path) != plan["code"][name]:
                raise ValueError("qualification code changed after the paired plan was locked")
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda ident: run(args.work, plan, ident), plan["cases"]))


if __name__ == "__main__":
    main()
