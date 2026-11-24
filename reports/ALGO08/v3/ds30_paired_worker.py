"""Run and independently validate one original DS30 publication."""

from io import BytesIO
import json
from math import isfinite
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic, process_time, time_ns

from ds30_paired_inputs import CALIBRATIONS, digest, read, write

STOCK = Path("/opt/leo-algo08/algo08v3/run")
PYTHON = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python")
TIMING_SCOPE = "raw_launcher_through_exit_plus_common_publication_verification"


def environment(work):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("ALGO08_") and key not in ("PYTHONPATH", "PYTHONHOME", "MPLBACKEND")}
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "MKL_NUM_THREADS",
                "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    env.update(TMPDIR=str(work / "tmp"), MPLCONFIGDIR=str(work / "fonts"), PYTHONDONTWRITEBYTECODE="1")
    return env


def original_options(recording, archive, offer, output):
    return ["--recording", recording, "--archive", archive, "--region", str(offer), "--bulk-root", str(output)]


def invocation(build, inputs, offer, authority, output, arm):
    common = original_options(inputs["authority"]["recording"], inputs["archive"], offer, output)
    if arm == "installed":
        return [str(STOCK), *common]
    return [str(PYTHON), "-IB", build["entry"], *common, "--authority", str(authority),
            "--authority-sha256", inputs["authority_sha256"], "--build", build["manifest"], "--build-sha256", build["sha256"]]


def child(command, directory, timeout, lease_fd):
    from tools.pipeline_eval.qualification.paired_publication import child_usage

    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        before, started, unix = child_usage(), monotonic(), time_ns()
        timed_out = False
        with subprocess.Popen(command, env=environment(directory), stdout=stdout, stderr=stderr,
                              pass_fds=(lease_fd,), start_new_session=True) as process:
            try:
                status = process.wait(timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    status = process.wait(5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    status = process.wait()
        elapsed, after = monotonic() - started, child_usage()
    return dict(elapsed_s=elapsed, started_unix_ns=unix, finished_unix_ns=time_ns(),
                exit_code=status, timed_out=timed_out, **{k: after[k] - count for k, count in before.items()})


def native_identity(native, authority, admitted, installed_detector=None):
    from leo.contracts.digests import canonical_digest

    source, provenance = native["source"], native["provenance"]
    raw = authority["raw_authority_sha256"]
    detector = provenance["detector_sha256"]
    if (source["raw_recording_authority_digest"] != raw or source["input_manifest_sha256"] != authority["inventory_sha256"]
            or source["session_id"] != authority["session_id"] or provenance["window_count"] != authority["window_count"]
            or provenance["processed_windows"] != admitted or len(source["probes"]) != 2 * admitted
            or native["clock_anchor"]["before"]["realtime_ns"] != authority["causal_cutoff_utc_ns"]
            or source["analysis_manifest_sha256"] != canonical_digest(["cancellation", raw, detector[7:], source["probes"]])
            or (installed_detector and detector != "sha256:" + installed_detector)):
        raise ValueError("The original native detector, hardware epochs or physical authority changed")


def publication(output, directory, arm, inputs, process, build):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from PIL import Image
    from tools.pipeline_eval.qualification import paired_publication as pairing

    authority, admitted = inputs["authority"], inputs["expected_admitted"]
    stock_detector = pairing.V3_IDENTITY["detector_sha256"] if arm == "installed" else None
    if process["exit_code"] or process["timed_out"]:
        result = dict(outcome="worker_failed", reason="timeout" if process["timed_out"] else "nonzero_exit")
        native_files = list((output / "fast-scan-automatic-work").glob("*/detections.json"))
        if len(native_files) == 1:
            native = native_files[0]
            native_identity(read(native), authority, admitted, stock_detector)
            result.update(raw_identity=authority, acquisition_verified=True, native_sha256=digest(native.read_bytes()))
            stderr = (directory / "stderr.log").read_text(errors="replace")
            if not process["timed_out"] and process["exit_code"] == 1 and pairing.orbit_solver_failure(stderr):
                handoff = pairing.failed_solver_evidence(output, inputs["offered_region"], {"exit_code": 1, "stderr": stderr})
                result.update(outcome="solver_failed", reached_solver=True, evidence=handoff, reason=handoff["reason"])
        return result
    if stock_detector:
        receipt = json.loads((directory / "stdout.log").read_text().splitlines()[-1])
        pairing.verify_v3_publication(output, receipt)
    else:
        marker = read(output / "algo08v3-successor-release.json")
        receipt = marker["receipt"]
        for key, expected in dict(build_sha256=build["sha256"], authority_sha256=inputs["authority_sha256"],
                                  archive_sha256=authority["archive_sha256"]).items():
            if marker[key] != expected:
                raise ValueError(f"Candidate marker changed {key}")
        if any(marker[key] != receipt[key] for key in ("session_id", "run_id", "terminal_sha256", "decision")):
            raise ValueError("Candidate marker differs from the standard receipt")
    evidence = pairing.evidence(output, receipt, process["started_unix_ns"], read_only=True)
    run = FastScanStore(output).automatic_workspace(receipt["run_id"], create=False)
    terminal = read(run / "terminal.json")
    native, = run.parent.glob("*/detections.json")
    native_bytes = native.read_bytes()
    observed = json.loads(native_bytes)
    native_identity(observed, authority, admitted, stock_detector)
    if (evidence["raw_authority"] != authority["raw_authority_sha256"]
            or receipt["session_id"] != authority["session_id"] or receipt["window_count"] != authority["window_count"]
            or receipt["counts"]["processed"] != admitted or receipt["region"] != inputs["offered_region"]
            or canonical_digest(observed) != terminal["native_sha256"]):
        raise ValueError("The terminal does not match the original authority, region and native packet")
    arms = evidence["arms"]
    if set(arms) != set(CALIBRATIONS):
        raise ValueError("Both calibrations must publish")
    figures, grid_points = [], None
    if receipt["decision"] == "complete":
        for row in arms.values():
            if len(row["latlon"]) != 2 or not all(isfinite(value) for value in (*row["latlon"], row["rf_rms_hz"])):
                raise ValueError("Invalid calibrated endpoint or RF RMS")
        store = FastStandardAnalysisStore(output)
        grid, trace = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
        position, = [item["sha256"] for item in evidence["artifacts"] if item["name"] == "position"]
        if not grid["complete"] or any(doc["binding"]["position_png_sha256"] != position for doc in (grid, trace)):
            raise ValueError("The numerical sidecars must bind their own verified position PNG")
        grid_points = grid["evaluated_points"]
        for item in evidence["artifacts"]:
            payload = store.artifact(receipt["run_id"], item["name"], item["sha256"])
            with Image.open(BytesIO(payload)) as image:
                if image.format != "PNG":
                    raise ValueError("Expected an encoded PNG")
                figures.append(dict(name=item["name"], sha256=item["sha256"],
                                    rgba_sha256=digest(image.convert("RGBA").tobytes()), size=list(image.size)))
    elif any(row["latlon"] is not None for row in arms.values()):
        raise ValueError("Withholding cannot return a position")
    return dict(outcome=receipt["decision"], raw_identity=authority, evidence=evidence,
                figures=figures, grid_points=grid_points, native_sha256=digest(native_bytes))


def run_attempt(directory, plan, inputs, offer, authority, arm, lease_fd, lease_id, generation, admission_io, sample):
    directory.mkdir()
    for name in ("tmp", "fonts"):
        (directory / name).mkdir()
    output = directory / "publication"
    if arm == "installed":
        # The named launcher resolves its existing empty bulk root strictly.
        output.mkdir()
    command = invocation(plan["candidate"], inputs, offer, authority, output, arm)
    write(directory / "launch.json", dict(command=command, arm=arm, lease_id=lease_id, generation=generation, io=admission_io,
                                         authority_sha256=inputs["authority_sha256"]))
    measured = child(command, directory, plan["timeout_s"], lease_fd)
    write(directory / "process.json", measured)
    began, cpu = monotonic(), process_time()
    try:
        result = publication(output, directory, arm, inputs, measured, plan["candidate"])
    except (IndexError, KeyError, OSError, TypeError, ValueError) as error:
        result = dict(outcome="invalid_publication", reason=f"{type(error).__name__}: {error}")
    validation = dict(elapsed_s=monotonic() - began, cpu_s=process_time() - cpu)
    complete = result["outcome"] in ("complete", "withheld")
    write(directory / "result.json", result | dict(algorithm=arm, timing_scope=TIMING_SCOPE if complete else "raw_launch_to_exit",
          elapsed_s=measured["elapsed_s"] + (validation["elapsed_s"] if complete else 0),
          cpu_s=measured["cpu_s"] + (validation["cpu_s"] if complete else 0),
          validation=validation, process=measured, lease_id=lease_id, generation=generation,
          authority_sha256=inputs["authority_sha256"], final_io=sample()))
