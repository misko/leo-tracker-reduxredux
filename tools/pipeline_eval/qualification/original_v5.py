"""Replay the pinned, full v5 scientific worker from its truth-free native bindings."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import nullcontext
from hashlib import file_digest
from pathlib import Path

from tools.pipeline_eval.scoring import ARMS, ROLES
from tools.pipeline_eval.variants import v5_lean as v5

BOUNDARY = "Native detector input to both original v5 decisions and validated scientific evidence"
EVIDENCE = "experimental-evidence.zip"
ROOT = Path(__file__).resolve().parents[3]
BULK = Path("/srv/bulk")
CACHE = v5.SOURCE.parents[1]
RUNNER_DIGESTS = {
    "evaluate_accuracy_repair.py": v5.RUNNER_SHA256,
    "evaluate_algo07.py": "sha256:d359c8652b60b82fb8f7f49780c282ad32f7a8754bf8ed0715dcd8ef08673e68",
    "evaluate_initial_discovery.py": (
        "sha256:bd93e839123c14e66a9b2beecd05a77d122d48fe366934976805d9f9f29dcfbc"
    ),
    "initial_discovery_archive.py": (
        "sha256:cf925b144d030f2bc83518b87846a59b2cd22d20fa54c8004a0b242e31a6d8a1"
    ),
}


def _no_fix(role, status, reason, elapsed=None):
    metrics = {"role": role}
    if elapsed is not None:
        metrics["candidate_s"] = elapsed
    return dict(
        status=status,
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms={arm: {"latlon": None} for arm in ARMS},
    )


def run(case: dict, work_dir: Path, role: str) -> dict:
    """Run one original policy. Local outputs outside bulk use a private bulk staging directory."""
    if role not in ROLES:
        raise ValueError(f"Unknown original v5 role: {role}")
    if case.get("panel") not in ("DS26", "DS29", "DS30"):
        return _no_fix(role, "unavailable", "Frozen v5 bindings are scoped to roof recordings")
    regions = case["regions"]
    if (
        len(regions) != 1
        or tuple(regions[0]["center"]) != v5.ROOF_CENTER
        or regions[0].get("width_km", v5.ROOF_WIDTH_KM) != v5.ROOF_WIDTH_KM
    ):
        return _no_fix(role, "unavailable", "Frozen v5 requires the original 25 km roof tile")
    for key, label in (
        ("native_path", "Native detector input"),
        ("request_path", "Frozen v5 request binding"),
    ):
        if not case.get(key) or not Path(case[key]).is_file():
            return _no_fix(role, "unavailable", f"{label} is unavailable")
    if not v5.PYTHON.is_file() or not v5.SOURCE.is_dir() or not v5.RUNNER.is_dir():
        return _no_fix(role, "unavailable", "Frozen v5 scientific runtime is unavailable")

    work_dir = Path(work_dir).resolve()
    if work_dir.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    work_dir.mkdir(parents=True, exist_ok=True)
    direct = work_dir.is_relative_to(BULK) or work_dir.is_relative_to(CACHE)
    scratch = Path(os.environ.get("LEO_PIPELINE_EVAL_V5_SCRATCH", BULK / "leo-dev")).resolve()
    if not direct and (not scratch.is_relative_to(BULK) or not scratch.is_dir()):
        return _no_fix(role, "unavailable", f"v5 staging needs a directory in {BULK}: {scratch}")
    paths = (
        nullcontext(work_dir)
        if direct
        else tempfile.TemporaryDirectory(prefix="pipeline-v5-", dir=scratch)
    )
    log_path = work_dir / "v5-worker.log"
    env = dict(
        os.environ,
        PYTHONPATH=f"{v5.SOURCE}:{v5.RUNNER}:{ROOT}",
        PYTHONSAFEPATH="1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1",
        BLIS_NUM_THREADS="1",
    )
    with log_path.open("xb") as log, paths as directory:
        destination = Path(directory)
        command = [
            "taskset",
            "-c",
            str(min(os.sched_getaffinity(0))),
            str(v5.PYTHON),
            "-B",
            "-m",
            "tools.pipeline_eval.qualification.original_v5",
            str(destination),
            role,
            str(Path(case["request_path"]).resolve()),
            str(Path(case["native_path"]).resolve()),
            case["id"],
            case.get("session_id") or "",
            case.get("native_sha256") or "",
        ]
        began = time.monotonic()
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            process.wait(timeout=v5.TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return _no_fix(
                role,
                "timed_out",
                f"Original v5 exceeded {v5.TIMEOUT_S} s",
                time.monotonic() - began,
            )
        finally:
            if process.poll() is None:
                v5._stop_process_tree(process.pid)
                process.wait()
        elapsed = time.monotonic() - began
        receipt = destination / "validated-archive.json"
        if process.returncode:
            with log_path.open("rb") as captured:
                captured.seek(max(0, captured.seek(0, os.SEEK_END) - 2048))
                lines = captured.read().decode(errors="replace").strip().splitlines()
            reason = lines[-1] if lines else f"Original v5 exited with code {process.returncode}"
            no_curvature = (
                "ValueError: Complete science and every PNG required: no_active_curvature"
            )
            stage_deadline = (
                "leo.operations.localization_v3_job.StageDeadline: "
                "Native job stage deadline exceeded"
            )
            status = {no_curvature: "withheld", stage_deadline: "timed_out"}.get(reason, "failed")
            return _no_fix(role, status, reason, elapsed)
        if not receipt.is_file():
            return _no_fix(role, "failed", "Original v5 did not validate its archive", elapsed)
        worker = v5._read(destination / "worker-result.json")
        if not direct:
            for name in (EVIDENCE, "experimental-request.json", "worker-result.json", receipt.name):
                with (destination / name).open("rb") as src, (work_dir / name).open("xb") as dst:
                    shutil.copyfileobj(src, dst)
        return _result(worker, elapsed)


def _result(worker, elapsed):
    timings = worker["stage_timings"]
    metrics = dict(
        role=worker["role"],
        policy=worker["policy"],
        candidate_s=elapsed,
        stages=[row["stage"] for row in timings],
        stage_s=[row["seconds"] for row in timings],
        request_sha256=worker["request_sha256"],
        source_sha256=worker["source_sha256"],
        native_manifest_sha256=worker["native_manifest_sha256"],
    )
    arms = {}
    for arm in ARMS:
        selected = worker["arms"][arm]
        arms[arm] = dict(latlon=selected["endpoint_latlon"], rf_rms_hz=selected["residual_rms_hz"])
        metrics[f"{arm}_frequency_score"] = selected["frequency_score"]
        metrics[f"{arm}_associated_observations"] = selected["associated_points"]
    return dict(
        status="ok",
        boundary=BOUNDARY,
        arms=arms,
        metrics=metrics,
        evidence=dict(file=EVIDENCE, sha256=worker["artifact"]["sha256"]),
    )


def _bind(
    request,
    role,
    policies,
    destination,
    native_path,
    case_id,
    session_id,
    native_sha256,
    digest,
):
    job = request["job"]
    native = job["native_input"]
    identity = job["identity"]
    if job["evaluation_reference"] is not None:
        raise ValueError("Evaluation reference is forbidden in inference input")
    if (session_id and identity["session_id"] != session_id) or (
        native_sha256 and native["sha256"] != native_sha256
    ):
        raise ValueError("Frozen v5 session or native content binding differs from its case")

    def run_id(configuration):
        binding = dict(
            case=case_id,
            repetition=0,
            role=configuration,
            source=request["source"]["sha256"],
            native=request["native_manifest"],
            input=native["sha256"],
        )
        return "experiment-" + digest(binding)[7:47]

    if identity["run_id"] != run_id("baseline"):
        raise ValueError("Baseline experimental identity differs from its frozen case")
    return dict(
        request,
        role=role,
        policy=policies[role],
        job=dict(
            job,
            output_root=str(destination),
            native_input=dict(native, path=native_path),
            identity=dict(identity, run_id=run_id(role)),
        ),
    )


def _worker(directory, role, request_path, native_path, case_id, session_id, native_sha256):
    for name, expected in RUNNER_DIGESTS.items():
        with (v5.RUNNER / name).open("rb") as stream:
            if "sha256:" + file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Frozen original v5 worker binding changed: {name}")

    import evaluate_accuracy_repair as original

    request = v5._read(request_path)
    if (
        set(request) != v5.REQUEST_KEYS
        or request["schema_version"] != 1
        or request["role"] != "baseline"
        or request["policy"] != original.POLICIES["baseline"]
        or request["model"] != original.MODEL
        or Path(request["source"]["root"]) != v5.SOURCE
        or request["source"]["sha256"] != v5.SOURCE_SHA256
    ):
        raise ValueError("Frozen original v5 baseline request required")
    destination = original.bulk_output(directory)
    worker_outputs = (
        EVIDENCE,
        "worker-result.json",
        "worker-result.partial",
        "validated-archive.json",
        "validated-archive.partial",
        "receipts",
    )
    paths = (destination / name for name in worker_outputs)
    if any(path.exists() or path.is_symlink() for path in paths):
        raise ValueError("Fresh original v5 worker output directory required")
    request = _bind(
        request,
        role,
        original.POLICIES,
        destination,
        native_path,
        case_id,
        session_id,
        native_sha256,
        original.ev.digest,
    )
    request_file = destination / "experimental-request.json"
    with request_file.open("x") as stream:
        json.dump(request, stream, allow_nan=False)
    print(
        json.dumps(
            dict(
                event="worker_binding",
                role=role,
                policy=request["policy"],
                request_sha256=original.ev.digest(request),
            )
        ),
        flush=True,
    )
    original.execute_worker(request_file)
    worker = v5._read(destination / "worker-result.json")
    if (
        worker["model"] != original.MODEL
        or worker["status"] != "complete"
        or worker["role"] != request["role"]
        or worker["policy"] != request["policy"]
        or worker["request_sha256"] != original.ev.digest(request)
        or worker["source_sha256"] != request["source"]["sha256"]
        or worker["native_manifest_sha256"] != original.ev.digest(request["native_manifest"])
        or worker["artifact"]["path"] != str(destination / EVIDENCE)
        or set(worker["arms"]) != set(ARMS)
        or set(worker["prediction_rows"]) != set(ARMS)
    ):
        raise ValueError("Original v5 result differs from its worker bindings")
    validation = original.inspect_artifact_cached(request, worker)
    if validation != "fresh":
        raise ValueError("A fresh original v5 archive validation is required")
    print(
        json.dumps(
            dict(
                event="validated_archive",
                sha256=worker["artifact"]["sha256"],
                request_sha256=worker["request_sha256"],
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    _worker(*sys.argv[1:])
