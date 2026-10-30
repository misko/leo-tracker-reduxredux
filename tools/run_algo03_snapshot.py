"""One guarded ALGO03 launcher for production and frozen dataset exports."""

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from algo03_shadow_worker import POLICY, read, write
from run_algo03_shadow import check_read_audit
from stage_algo03_release import MANIFEST, MANIFEST_SHA256

from leo.contracts.fast_graph_position import validate_terminal

ROOT = Path(__file__).resolve().parents[1]


def copy_snapshot(descriptor_path, destination):
    descriptor_path = Path(descriptor_path).resolve(strict=True)
    source = descriptor_path.parent / "inference"
    descriptor = read(descriptor_path)
    if Path(descriptor["root"]).resolve() != source.resolve():
        raise ValueError("Snapshot inference root does not belong to its descriptor")
    baseline = validate_terminal(descriptor["terminal"], input_sha256=descriptor["input_sha256"])
    if baseline["state"] != "complete" or baseline["session_id"] != descriptor["session_id"]:
        raise ValueError("Snapshot lacks a qualified recording baseline")
    destination.mkdir(parents=True, exist_ok=False)
    for relative, expected in descriptor["files"].items():
        name = Path(relative)
        original = source / name
        if (
            name.is_absolute()
            or ".." in name.parts
            or original.is_symlink()
            or not original.resolve(strict=True).is_relative_to(source.resolve())
        ):
            raise ValueError("Snapshot member escapes its inference root")
        if "sha256:" + hashlib.sha256(original.read_bytes()).hexdigest() != expected:
            raise ValueError("Snapshot source changed")
        target = destination / "inference" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError("Snapshot copy differs from source")
    tracking = destination / "inference/SCAN/tracking.json"
    if "sha256:" + hashlib.sha256(tracking.read_bytes()).hexdigest() != descriptor["input_sha256"]:
        raise ValueError("Snapshot tracking input digest differs")
    document = read(tracking)
    if document.get("source", document)["session_id"] != descriptor["session_id"]:
        raise ValueError("Snapshot input belongs to another recording")
    descriptor = dict(descriptor, root=str(destination / "inference"))
    write(destination / "descriptor.json", descriptor)
    return descriptor


def run_snapshot(descriptor_path, output, *, deadline, proof_reserve_seconds=30):
    """Copy, qualify and run under the caller's original whole-recovery deadline."""
    began = time.monotonic()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = read(ROOT / MANIFEST)
    if hashlib.sha256((ROOT / MANIFEST).read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Frozen ALGO03 manifest changed")
    for relative, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen ALGO03 member changed: " + relative)
    descriptor = copy_snapshot(descriptor_path, output / "snapshot")
    result = dict(
        baseline=descriptor["terminal"],
        selected=None,
        decision="ALGO02_fallback",
        failure="Recovery preparation exhausted its whole-job budget",
    )
    remaining = min(1170, int(deadline - time.monotonic() - proof_reserve_seconds))
    if remaining < 1:
        return result
    write(
        output / "launch.json",
        dict(
            policy=POLICY,
            maximum_seconds=remaining,
            whole_recovery_deadline_monotonic=deadline,
            frozen_manifest_sha256=MANIFEST_SHA256,
            adapter_hashes={
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in (
                    "tools/run_algo03_snapshot.py",
                    "tools/algo03_production_worker.py",
                    "tools/algo03_shadow_worker.py",
                    "tools/algo03_inventory.py",
                )
            },
        ),
    )
    environment = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        PYTHONPATH=os.pathsep.join(
            map(str, (ROOT / "deploy/fast_graph_guard", ROOT / "src", ROOT / "tools"))
        ),
        LEO_FAST_GRAPH_RUN_ROOT=str(output),
        LEO_FAST_GRAPH_INPUT=str(output / "snapshot/inference/SCAN/tracking.json"),
        LEO_FAST_GRAPH_SOURCE_ROOT=str(ROOT),
        LEO_FAST_GRAPH_TLE_ROOT=str(output / "unused-tle-archive"),
        MPLCONFIGDIR=str(output / "matplotlib-cache"),
    )
    command = [
        sys.executable,
        "-B",
        str(ROOT / "tools/algo03_shadow_worker.py"),
        "--output",
        str(output),
        "--maximum-seconds",
        str(remaining),
    ]
    with (output / "worker.log").open("xb") as log:
        child = subprocess.Popen(
            command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            code = child.wait(timeout=max(1, deadline - time.monotonic() - 20))
        except BaseException:
            child.terminate()
            try:
                # The root's execute() needs up to three seconds to terminate
                # each scientific process group. Allow that cleanup to finish.
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            raise
    audit = check_read_audit(output, child.pid)
    if code == 0 and (output / "decision.json").exists():
        result = read(output / "decision.json")
    else:
        result["failure"] = "Recovery worker failed"
    if not audit["verified"]:
        result.update(
            selected=None, decision="ALGO02_fallback", failure="Recovery read audit failed"
        )
    result.update(read_audit=audit, total_seconds=time.monotonic() - began)
    write(output / "terminal.json", result)
    return result
