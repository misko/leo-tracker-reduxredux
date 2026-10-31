"""Publish ALGO04 only after guarded replay and preservation of its ALGO03 incumbent."""

import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

from algo03_production_worker import envelope as proof_envelope
from algo03_production_worker import verify_selected
from algo03_shadow_worker import read, write
from run_algo03_shadow import check_read_audit

from leo.contracts.fast_graph_position import KIND
from leo.contracts.fast_graph_position_v3 import (
    MODEL_VERSION,
    candidate_admission,
    validate_terminal,
)
from leo.storage.fast_graph_position_v2 import FastGraphPositionStoreV2

ROOT = Path(__file__).resolve().parents[1]
POLICY = "algo04-conditional-numerical-replay-v1"


def verify_release():
    from stage_algo04_release import MANIFEST, MANIFEST_SHA256

    payload = (ROOT / MANIFEST).read_bytes()
    if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Immutable ALGO04 manifest changed")
    manifest = read(ROOT / MANIFEST)
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("ALGO04 scientific dependency changed: " + name)


def envelope(incumbent, candidate, *, numerical_seconds, failure=None):
    admitted, reason = candidate_admission(incumbent, candidate)
    terminal = dict(
        schema_version=3,
        kind=KIND,
        model_version=MODEL_VERSION,
        state="complete",
        input_sha256=incumbent["input_sha256"],
        session_id=incumbent["session_id"],
        incumbent=incumbent,
        candidate=candidate,
        decision="ALGO04_additive" if admitted else "ALGO03_fallback",
        position=(candidate if admitted else incumbent)["position"],
        reference_usage="none",
        future_TLE_used=False,
        matched_c_inputs=True,
        selected_arm="fitted_c",
        incumbent_seconds=incumbent["total_seconds"],
        numerical_seconds=numerical_seconds,
        total_seconds=incumbent["total_seconds"] + numerical_seconds,
        acceptance_reason=reason,
        failure=failure,
        recovery_policy=POLICY,
    )
    return validate_terminal(terminal, input_sha256=incumbent["input_sha256"])


def guarded_replay(output, *, deadline):
    remaining = min(1170, int(deadline - time.monotonic() - 30))
    if remaining < 1:
        raise TimeoutError("ALGO04 preparation consumed its bounded recovery budget")
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
        str(ROOT / "tools/algo04_replay_worker.py"),
        "--output",
        str(output),
        "--maximum-seconds",
        str(remaining),
    ]
    write(output / "launch.json", dict(policy=POLICY, command=command, maximum_seconds=remaining))
    with (output / "worker.log").open("xb") as log:
        child = subprocess.Popen(
            command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            code = child.wait(timeout=max(1, deadline - time.monotonic() - 20))
        except BaseException:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            raise
    audit = check_read_audit(output, child.pid)
    if code != 0 or not (output / "decision.json").exists():
        raise ValueError("ALGO04 guarded worker failed; retain its log and read receipts")
    result = read(output / "decision.json")
    result["read_audit"] = audit
    write(output / "guarded-result.json", result)
    if not audit["verified"]:
        raise ValueError("ALGO04 process read audit failed")
    return result


def run(args):
    began = time.monotonic()
    verify_release()
    store = FastGraphPositionStoreV2(args.bulk_root)
    job = store.status(args.job)
    if not job or job["state"] != "complete":
        raise ValueError("Completed published ALGO03 source required")
    incumbent, before = store.terminal(job)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    recovery = output / "recovery"
    recovery.mkdir()
    candidate, failure = None, None
    try:
        if not (incumbent.get("read_audit") or {}).get("verified"):
            raise ValueError("Historical incumbent read audit not verified; retain ALGO03")
        store.export_recovery(job, recovery / "source-export")
        result = guarded_replay(recovery, deadline=began + args.maximum_seconds)
        if result.get("baseline") != incumbent["baseline"]:
            raise ValueError("Replay changed the original ALGO02 comparator")
        checks = verify_selected(result, recovery) if result.get("selected") else None
        candidate = proof_envelope(
            incumbent["baseline"],
            result,
            recovery_seconds=time.monotonic() - began,
            proof_checks=checks,
        )
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
    current, after = store.terminal(job)
    if before != after or incumbent != current:
        raise ValueError("Published ALGO03 incumbent changed during numerical replay")
    terminal = envelope(
        incumbent, candidate, numerical_seconds=time.monotonic() - began, failure=failure
    )
    write(output / "terminal.json", terminal)
    return terminal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--job", required=True, help="Completed source ALGO03/v2 job ID")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=int, choices=range(1, 1201), default=1200)
    run(parser.parse_args())
