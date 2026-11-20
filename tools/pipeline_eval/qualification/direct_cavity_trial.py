"""Build and qualify a self-contained compact cavity source tree."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter, time_ns
from unittest.mock import patch

from ..__main__ import local_output, read_predictions, save_json
from ..scoring import validate_result
from ..variants import orbit_projector, v5_direct_cavity, v5_lean, v5_secant_fit
from . import full_receiver_comparison as common
from . import working_memory_trial
from .native_agreement_cascade_eval import compact_wall
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = common.SCREEN / "streamlined/direct-cavity"
RELEASE = "staged"
STOCK, DIRECT = "v5_secant_fit", v5_direct_cavity.METHOD
CAP, NICE = 170, 10
SALT = "direct-cavity-holdout-v1:"
PRIOR = common.SCREEN / "deployment/same-core-baseline/source-lock.json"
CANON = common.SCREEN / "secant-full"
BASELINE = {
    "ordinary-DS26-0036": (4, (STOCK, DIRECT)),
    "ordinary-DS29-0082": (5, (DIRECT, STOCK)),
    "capture-era-DS26-0026": (6, (STOCK, DIRECT)),
}
VARIANTS = "tools/pipeline_eval/variants/"
ENTRY = VARIANTS + "v5_direct_cavity.py"
PARTS = (
    "tools/pipeline_eval/__init__.py",
    VARIANTS + "__init__.py",
    ENTRY,
    VARIANTS + "compact_cavity_optimizer.py",
    VARIANTS + "orbit_projector.py",
    VARIANTS + "orbit_projector.c",
    VARIANTS + "v5_core.py",
    VARIANTS + "v5_lean.py",
)
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile")


def held_case():
    archived = CANON / "v5_secant_fit.jsonl.gz"
    lock = common.seal(CANON, "prediction-lock.json", (archived.name,))
    old = set(common.read(PRIOR)["cases"])
    old.update("-".join(key.rsplit("-", 2)[-2:]) for key in BASELINE)
    eligible = [
        row
        for row in read_predictions(archived).values()
        if row["id"] not in old and row["result"]["status"] == "ok" and compact_wall(row) < 120
    ]
    chosen = min(eligible, key=lambda row: hashlib.sha256((SALT + row["id"]).encode()).digest())
    return dict(
        id=chosen["id"],
        salt=SALT,
        eligible=len(eligible),
        historical_wall_s=compact_wall(chosen),
        archive_sha256=lock["files"][archived.name],
        methodology=common.sha(PRIOR),
    )


def input_case(key):
    case, tags = working_memory_trial.case_binding(key, working_memory_trial.RAW)
    req = Path(case["request_path"])
    request = common.read(req)
    job = request["job"]
    archive = Path(job["tle_root"])
    snapshots = {p.name: common.sha(p) for p in archive.rglob("*.tle")}
    if snapshots != {k: v.removeprefix("sha256:") for k, v in request["causal_snapshots"].items()}:
        raise ValueError("causal TLE archive differs from the frozen request")
    if job["native_input"]["sha256"] != case["native_sha256"]:
        raise ValueError("native file does not bind the requested input")
    return (
        case,
        request,
        dict(
            tags,
            id=case["id"],
            tile=case["regions"][0],
            input_sha256=working_memory_trial.canonical_request(req),
            frozen_request_sha256=common.sha(req),
        ),
    )


def command_env(bundle):
    return dict(
        os.environ,
        PYTHONPATH=str(bundle),
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        BLIS_NUM_THREADS="1",
        PYTHONNOUSERSITE="1",
    )


def sources():
    own = (Path(__file__), REPORT / "PROTOCOL.md", *(common.ROOT / name for name in PARTS))
    return dict(
        files={str(p.relative_to(common.ROOT)): common.sha(p) for p in own},
        compact=common.secant_full.secant.frozen_sources(),
        frozen=v5_lean.SOURCE_SHA256,
    )


def build(work, source, expected_binary):
    stage = work / RELEASE
    stage.mkdir(exist_ok=False)
    entries = source["files"]
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if "sha256:" + hashlib.sha256(canonical.encode()).hexdigest() != v5_lean.SOURCE_SHA256:
        raise ValueError("unknown frozen receiver release")
    files = {name: v5_lean.SOURCE / name for name in entries}
    files.update({name: common.ROOT / name for name in PARTS})
    copies = {}
    for name, path in files.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        observed = hashlib.sha256(raw).hexdigest()
        if name in entries and "sha256:" + observed != entries[name]:
            raise ValueError(f"frozen numerical source has changed: {name}")
        target.write_bytes(raw)
        copies[name] = observed
    script = (
        "from leo.analysis.localization_v4.backend import build_native; "
        "import sys; build_native(sys.argv[1])"
    )
    subprocess.run(
        [str(v5_lean.PYTHON), "-B", "-c", script, str(stage / "native")],
        cwd=stage,
        env=command_env(stage),
        check=True,
        timeout=40,
    )
    binary = common.sha(stage / "native/native_bound.so")
    if binary != expected_binary:
        raise ValueError("rebuilt native bound binary differs from the sealed original")
    save_json(
        work / "bundle.json", dict(frozen_source=source["sha256"], files=copies, binary=binary)
    )


def lock(work):
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    known = sources()
    held = held_case()
    plan = dict(BASELINE, **{f"capture-era-{held['id']}": (4, (DIRECT, STOCK))})
    inputs = {key: input_case(key) for key in plan}
    _, anchor, _ = next(iter(inputs.values()))
    expected_binary = anchor["native_manifest"]["binary_sha256"]
    if any(
        row[1]["native_manifest"]["binary_sha256"] != expected_binary for row in inputs.values()
    ):
        raise ValueError("paired cases have different numerical bound versions")
    build(work, anchor["source"], expected_binary)
    save_json(
        work / "plan.json",
        dict(
            cases=plan,
            sources=known,
            held=held,
            bindings={k: v[2] for k, v in inputs.items()},
            bundle_sha256=common.sha(work / "bundle.json"),
            sealed_ns=time_ns(),
            cap_s=CAP,
        ),
    )


def direct_command(case, job, bundle, library):
    items = dict(
        native=case["native_path"],
        native_sha256=case["native_sha256"],
        track_config=job["track_config"]["path"],
        config_sha256=job["track_config"]["sha256"],
        session=case["session_id"],
        archive=job["tle_root"],
        native_backend=str(bundle / "native/manifest.json"),
        library=str(library),
    )
    return [
        str(v5_lean.PYTHON),
        "-B",
        "-m",
        "tools.pipeline_eval.variants.v5_direct_cavity",
        *(part for key, value in items.items() for part in ("--" + key.replace("_", "-"), value)),
        "--tile",
        *map(str, job["search_center"]),
        "--screen-center",
        *map(str, job["screen_center"]),
    ]


def direct_run(case, job, work, out):
    stage = work / RELEASE
    library, result, log = out / "orbit_projector.so", out / "result.json", out / "worker.log"
    begin = perf_counter()
    subprocess.run(
        [
            "cc",
            *orbit_projector.FLAGS,
            str(stage / (VARIANTS + "orbit_projector.c")),
            "-lm",
            "-o",
            str(library),
        ],
        check=True,
        timeout=10,
    )
    command = direct_command(case, job, stage, library)
    with result.open("xb") as dst, log.open("xb") as stderr:
        try:
            child = subprocess.run(
                command,
                cwd=stage,
                env=command_env(stage),
                stdout=dst,
                stderr=stderr,
                timeout=max(1, CAP - 2 - (perf_counter() - begin)),
            )
        except subprocess.TimeoutExpired:
            return v5_lean._no_fix("Direct worker reached its 170 s cap", status="timed_out")
    if child.returncode:
        lines = log.read_text(errors="replace").strip().splitlines()
        return v5_lean._no_fix(lines[-1] if lines else f"Exit {child.returncode}", status="failed")
    return common.read(result)


def replay(work, key, method):
    work = local_output(work)
    plan = common.read(work / "plan.json")
    cpu, order = plan["cases"][key]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < NICE or sources() != plan["sources"]:
        raise ValueError("execution environment differs from the preregistered source or pin")
    bundle_path = work / "bundle.json"
    if common.sha(bundle_path) != plan["bundle_sha256"]:
        raise ValueError("staged release manifest has changed")
    stage, manifest = work / RELEASE, common.read(bundle_path)
    if any(common.sha(stage / name) != value for name, value in manifest["files"].items()):
        raise ValueError("staged source has changed")
    if common.sha(stage / "native/native_bound.so") != manifest["binary"]:
        raise ValueError("staged numerical bound has changed")
    case, request, tags = input_case(key)
    if tags != plan["bindings"][key]:
        raise ValueError("sealed input changed")
    out = work / "runs" / key / method
    out.mkdir(parents=True, exist_ok=False)
    start, cpu_start = perf_counter(), cpu_s()
    if method == DIRECT:
        result = direct_run(case, request["job"], work, out)
    else:
        with patch.object(v5_lean, "TIMEOUT_S", CAP - 3):
            result = v5_secant_fit.run(case, out, "secant")
        if "exceeded its" in result.get("reason", ""):
            result["status"] = "timed_out"
        elif result["status"] == "unavailable":
            result["status"] = "failed"
        if working_memory_trial.canonical_request(out / "request.json") != tags["input_sha256"]:
            raise ValueError("stock materialized a different request")
    resources = stamp(start, cpu_start)
    validate_result(result)
    save_json(
        out / "prediction.json",
        dict(
            tags,
            key=key,
            method=method,
            cpu=cpu,
            order=order.index(method),
            result=result,
            resources=resources,
            plan_sha256=common.sha(work / "plan.json"),
        ),
    )
    print(key, method, result["status"], round(resources["wall_s"], 2), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="mode", required=True)
    modes.add_parser("lock").add_argument("work", type=Path)
    run = modes.add_parser("run")
    run.add_argument("work", type=Path)
    run.add_argument("key")
    run.add_argument("method", choices=(STOCK, DIRECT))
    args = p.parse_args()
    if args.mode == "lock":
        lock(args.work)
    else:
        replay(args.work, args.key, args.method)


if __name__ == "__main__":
    main()
