"""Run frozen fast v5 from native detector rows through the selected position."""

import json
import math
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

BOUNDARY = "Native detector input to both v5 position decisions"
ARMS = ("c0", "fitted_c")
ROOF_CENTER = (37.906, -122.545)
ROOF_WIDTH_KM = 25.0
SOURCE = Path("/home/mouse9911/.cache/accuracy-repair-20261115/frozen-001/src")
SOURCE_SHA256 = "sha256:36be340683b030af69ed99194d3c8fbe976093d49d16c4cfb7be4960344898ae"
RUNNER = Path("/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001/runner/tools")
RUNNER_SHA256 = "sha256:a7fe0b3386fddcc6cc8ff6f25c5e27186744bccd7292b1688bcdbc4c5001a408"
PYTHON = Path(__file__).resolve().parents[3] / ".venv/bin/python"
TIMEOUT_S = 1200
REQUEST_KEYS = {
    "schema_version",
    "model",
    "role",
    "policy",
    "source",
    "native_manifest",
    "causal_snapshots",
    "job",
}


def _no_fix(reason, *, status="unavailable", metrics=None):
    return dict(
        status=status,
        reason=reason,
        boundary=BOUNDARY,
        metrics={} if metrics is None else metrics,
        arms={arm: {"latlon": None} for arm in ARMS},
    )


def _read(path):
    return json.loads(Path(path).read_bytes())


def _stop_process_tree(pid):
    # The worker shares the evaluation process group so an outer timeout can stop it.
    # A standalone timeout can only signal the variant's own worker and numerical children.
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGSTOP)
    children = Path(f"/proc/{pid}/task/{pid}/children")
    with suppress(FileNotFoundError, ProcessLookupError):
        for child in children.read_text().split():
            _stop_process_tree(int(child))
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


def run(case: dict, work_dir: Path) -> dict:
    """Request bindings supply the frozen configuration and causal TLE archive."""
    return run_bound_worker(case, work_dir, Path(__file__))


def run_bound_worker(case: dict, work_dir: Path, script: Path, *, worker_args=()) -> dict:
    if case.get("panel") not in ("DS26", "DS29"):
        return _no_fix("Frozen native v5 bindings are available only for roof recordings")
    regions = case["regions"]
    if (
        len(regions) != 1
        or tuple(regions[0]["center"]) != ROOF_CENTER
        or regions[0].get("width_km", ROOF_WIDTH_KM) != ROOF_WIDTH_KM
    ):
        return _no_fix("Frozen v5 is scoped to the original single 25 km roof tile")
    if not case.get("native_path") or not Path(case["native_path"]).is_file():
        return _no_fix("Native detector input is unavailable")
    if not case.get("request_path") or not Path(case["request_path"]).is_file():
        return _no_fix("Frozen v5 request binding is unavailable")
    request = _read(case["request_path"])
    job = request["job"]
    native = job["native_input"]
    if job["evaluation_reference"] is not None:
        return _no_fix("Evaluation reference is forbidden in inference input")
    for key, expected in (
        ("native_sha256", native["sha256"]),
        ("session_id", job["identity"]["session_id"]),
    ):
        if case.get(key) is not None and case[key] != expected:
            return _no_fix(f"Case {key} differs from its frozen v5 binding")
    if not PYTHON.is_file() or not SOURCE.is_dir() or not RUNNER.is_dir():
        return _no_fix("Frozen v5 numerical runtime is unavailable")

    work_dir = Path(work_dir).resolve()
    if work_dir.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    work_dir.mkdir(parents=True, exist_ok=True)
    job["output_root"] = str(work_dir)
    native["path"] = str(Path(case["native_path"]).resolve())
    request_file = work_dir / "request.json"
    result_file = work_dir / "result.json"
    with request_file.open("x") as stream:
        json.dump(request, stream, allow_nan=False)
    command = [
        "taskset",
        "-c",
        str(min(os.sched_getaffinity(0))),
        str(PYTHON),
        "-B",
        str(script.resolve()),
        str(request_file),
        str(result_file),
        *worker_args,
    ]
    env = dict(
        os.environ,
        PYTHONPATH=f"{SOURCE}:{RUNNER}:{Path(__file__).resolve().parents[3]}",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    log_path = work_dir / "worker.log"
    with log_path.open("xb") as log:
        began = time.monotonic()
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            process.wait(timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return _no_fix(
                f"Frozen v5 inference exceeded its {TIMEOUT_S} s deadline",
                metrics={"candidate_s": time.monotonic() - began},
            )
        finally:
            if process.poll() is None:
                _stop_process_tree(process.pid)
                process.wait()
        elapsed = time.monotonic() - began
    if process.returncode or not result_file.is_file():
        with log_path.open("rb") as log:
            log.seek(max(0, log.seek(0, os.SEEK_END) - 1000))
            lines = log.read().decode(errors="replace").strip().splitlines()
        return _no_fix(
            lines[-1] if lines else f"Frozen v5 worker exited with code {process.returncode}",
            metrics={"candidate_s": elapsed},
        )
    result = _read(result_file)
    result["metrics"]["candidate_s"] = elapsed
    return result


def endpoint_latlon(region, x):
    point = [float(value) for value in region.latlon(x)]
    if len(point) != 2 or not all(math.isfinite(value) for value in point):
        raise ValueError("Invalid selected position")
    return point


def _position_result(inference, **_):
    # run_native calls this only after its final scientific decision.
    arms = {}
    metrics = dict(
        native_observations=len(inference["native"]["observations"]),
        tracks=len(inference["native"]["tracks"]),
    )
    for arm in ARMS:
        selected = inference["arms"][arm]
        problem, x = inference["context"]["problems"][arm]
        point = endpoint_latlon(problem.scan.search_region, x)
        if not all(
            math.isclose(calculated, expected, abs_tol=1e-9, rel_tol=0)
            for calculated, expected in zip(point, selected["endpoint_latlon"], strict=True)
        ):
            raise ValueError(f"Selected position changed for {arm}")
        arms[arm] = {"latlon": point}
        metrics[f"{arm}_associated_observations"] = len(inference["owners"][arm])
        for name, value in (
            ("frequency_score", selected.get("negative_twice_elbo", selected.get("objective"))),
            ("conditional_rms_hz", selected.get("RMS_hz", selected.get("rms_hz"))),
        ):
            if value is not None and math.isfinite(value):
                metrics[f"{arm}_{name}"] = float(value)
    return dict(
        status="ok",
        boundary=BOUNDARY,
        arms=arms,
        metrics=metrics,
        stage_timings=inference["stage_timings"],
    )


def bound_request(request_path):
    import evaluate_accuracy_repair as original

    request = _read(request_path)
    source = request["source"]
    if (
        set(request) != REQUEST_KEYS
        or request["schema_version"] != 1
        or request["role"] != "baseline"
        or request["policy"] != original.POLICIES["baseline"]
        or request["model"] != original.MODEL
        or Path(source["root"]) != SOURCE
        or source["sha256"] != SOURCE_SHA256
    ):
        raise ValueError("Frozen original no-repair v5 request required")
    if original.ev.file_digest(Path(original.__file__)) != RUNNER_SHA256:
        raise ValueError("Frozen v5 worker changed")
    from leo.operations.localization_v3_job import runtime_versions, validate_request

    job = validate_request(request["job"])
    if runtime_versions() != job["runtime"]:
        raise ValueError("Numerical runtime differs from frozen request")
    if original.ev.source_binding(SOURCE) != source:
        raise ValueError("Frozen source binding changed")
    original.check_scientific_inputs(request)
    return original, request, job


def _worker(request_path, result_path):
    original, request, job = bound_request(request_path)
    source = request["source"]
    engine = original.ev.owned_import("leo.application.localization_v3_engine", source)
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.operations.localization_v3_job import read_bound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.tle_archive import TleArchiveReader

    destination = original.ev.local_output(job["output_root"])

    def emit(event):
        print(json.dumps(event, sort_keys=True, allow_nan=False), flush=True)

    ports, _ = original.execution_ports(request, destination / "receipts", emit)
    document = read_bound(job["native_input"])
    if document["source"]["session_id"] != job["identity"]["session_id"]:
        raise ValueError("Native input belongs to another session")
    # Keep the frozen engine and its numerical policy intact in this dedicated process.
    engine.render_inference = _position_result
    result = engine.run_native(
        document,
        TleArchiveReader(Path(job["tle_root"])),
        TrackConfig(**read_bound(job["track_config"])["config"]),
        SearchRegion(tuple(job["search_center"])),
        identities=job["scan_identities"],
        execution=ports,
        screen_latitude_deg=job["screen_center"][0],
        screen_longitude_deg=job["screen_center"][1],
        title=job["title"],
        evaluation_reference=None,
        on_stage=lambda row: emit(dict(event="stage", **row)),
    )
    timings = result["stage_timings"]
    if result["status"] == "no_active_curvature":
        result = _no_fix("Track preparation found no active curvature", status="withheld")
    else:
        result = {key: result[key] for key in ("status", "boundary", "arms", "metrics")}
    result["metrics"].update(
        stages=[row["stage"] for row in timings],
        stage_s=[row["seconds"] for row in timings],
    )
    original.check_scientific_inputs(request)
    if original.ev.source_binding(SOURCE) != source:
        raise ValueError("Frozen source changed during inference")
    original.write(result_path, result)


if __name__ == "__main__":
    _worker(*sys.argv[1:])
