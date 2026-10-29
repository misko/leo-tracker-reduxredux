"""Bounded production adapter for the validated causal ALGO02 composition.

Each invocation owns a fresh directory. Original numerical routines are reused
without archived endpoints, post-observation elements, or evaluation geography.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

from leo.contracts.fast_graph_position import KIND, MODEL_VERSION, validate_terminal


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def persist(path, value):
    import numpy as np

    def encode(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(type(value).__name__)

    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False, default=encode)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def prepare(root, case, tle_root):
    import evaluate_ds22_merged_tracks as config
    import evaluate_ds23_phase_refreshed as graph
    import ds23_radio_noise as noise
    import prepare_ds23_genuine_causal_prior as prior
    import export_ds23_causal_history as history
    import learn_ds23_causal_phase_forecast as forecast
    from leo.operations.tle_archive import TleArchiveReader

    # Bind public archive/configuration ports in this isolated preparation process.
    reader = lambda ignored: TleArchiveReader(tle_root)
    graph.TleArchiveReader = reader
    prior.TleArchiveReader = reader
    history.TleArchiveReader = reader
    graph.CONFIG = config.CONFIG = ROOT / "deploy/config/fast-graph-tracklets-v1.json"
    graph.OUTPUT = root
    graph.prepare(case)
    prepared = json.loads((root / case / "prepared.json").read_text())
    if prepared["status"] != "prepared":
        return
    noise.run(root / case)
    prior.SOURCE, prior.OUTPUT = root, root / "causal_prior"
    prior.run(case)
    history.SOURCE = root
    folder = root / "causal_phase_history"
    folder.mkdir()
    path = folder / (case + ".json")
    persist(path, history.export(case))
    forecast.run(path)


class Deadline(BaseException):
    pass


def run(input_path, output, *, maximum_seconds=1200, tle_root=Path("/var/lib/leo/tle")):
    input_path, output = Path(input_path).resolve(), Path(output).resolve()
    if not 1 <= maximum_seconds <= 1200:
        raise ValueError("Whole-job budget must be 1..1200 seconds")
    if output == input_path or output in input_path.parents:
        raise ValueError("Output overlaps input")
    output.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    payload = input_path.read_bytes()
    input_hash = "sha256:" + hashlib.sha256(payload).hexdigest()
    terminal = dict(schema_version=1, kind=KIND, model_version=MODEL_VERSION,
                    input_sha256=input_hash, state="failed", position=None,
                    reference_usage="none", future_TLE_used=False,
                    region_center=[37.906, -122.545], box_width_km=25.,
                    start_east_north_km=[0., 0.], selected_arm="fitted_c")
    persist(output / "launch.json", dict(terminal, input_path=str(input_path),
            maximum_seconds=maximum_seconds, source_revision=revision()))
    case = "SCAN"  # Data identifiers must never select different inference paths.
    workspace = output / "inference"
    directory = workspace / case
    directory.mkdir(parents=True)
    (directory / "tracking.json").write_bytes(payload)
    persist(directory / "input_receipt.json", dict(status="exported",
            adapter="fast_tracking_contract", tracking_sha256=input_hash.split(":")[1]))
    stages = [("prepare", [sys.executable, "-B", str(Path(__file__)), "--prepare",
               "--root", str(workspace), "--case", case, "--tle-root", str(tle_root)]),
              ("algo02", [sys.executable, "-B", str(ROOT / "tools/algo02_scan.py"),
               "--run-dir", str(workspace), "--case", case, "--stage", "all"]),
              ("family", [sys.executable, "-B", str(ROOT / "tools/fast_graph_engine.py"),
               "--root", str(workspace), "--case", case])]
    terminal["stages"] = []
    try:
        document = json.loads(payload)
        source = document["source"]
        terminal["session_id"] = source["session_id"]
        if source["sample_rate_hz"] not in (2_500_000, 5_000_000, 10_000_000):
            raise ValueError("Unsupported fast-scan capture rate")
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                PYTHONPATH=os.pathsep.join((str(ROOT / "deploy/fast_graph_guard"), str(ROOT / "src"), str(ROOT / "tools"))),
                LEO_FAST_GRAPH_RUN_ROOT=str(output), LEO_FAST_GRAPH_INPUT=str(input_path),
                LEO_FAST_GRAPH_SOURCE_ROOT=str(ROOT),
                LEO_FAST_GRAPH_TLE_ROOT=str(Path(tle_root).resolve()),
                MPLCONFIGDIR=str(output / "matplotlib-cache"))
        for name, command in stages:
            remaining = maximum_seconds - (time.monotonic() - began)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, maximum_seconds)
            mark = time.monotonic()
            with (output / (name + ".log")).open("xb") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           env=environment, cwd=ROOT)
                try:
                    code = process.wait(timeout=remaining)
                except BaseException:
                    # The outer supervisor also kills the entire process group.
                    process.kill()
                    process.wait()
                    raise
            terminal["stages"].append(dict(stage=name, returncode=code,
                                           process_id=process.pid, seconds=time.monotonic() - mark))
            if code:
                raise RuntimeError(name + " failed; see retained stage log")
            if name == "prepare":
                status = json.loads((directory / "prepared.json").read_text())["status"]
                if status != "prepared":
                    terminal.update(state="unavailable", reason=status)
                    break
            if name == "algo02":
                status = json.loads((directory / "algo02_result.json").read_text())["status"]
                if status != "accepted":
                    terminal.update(state="unavailable", reason="no_qualified_ALGO02_pair")
                    break
        else:
            result = json.loads((workspace / "family_cavity/position" / (case + ".json")).read_text())
            if result["status"] != "complete":
                raise ValueError("Family comparison is incomplete")
            arms = result["policy_arms"]
            for saved in arms.values():
                saved["phase_stability_required"] = "final_phase_change_s" in saved
                if not saved["phase_stability_required"]:
                    saved["final_phase_change_s"] = saved["history"][-1]["phase_change_s"]
            memberships = []
            for arm in ("c0", "fitted_c"):
                memberships.append([(t["component"], t["points"], t.get("norad"), t.get("observation_ids"))
                    for t in arms[arm]["gates"]["tracks"] + arms[arm].get("linear_gates", [])])
            if memberships[0] != memberships[1]:
                raise ValueError("Paired c-arm retained identities or observations differ")
            terminal.update(state="complete", arms=arms,
                qualification="paired_residual_phase_regional_gates", matched_c_inputs=True,
                family_replacement_accepted=result["accepted"],
                scientific_result_sha256=digest(workspace / "family_cavity/position" / (case + ".json")))
            lat, lon = terminal["arms"]["fitted_c"]["endpoint_latlon"]
            terminal["position"] = dict(latitude_deg=lat, longitude_deg=lon)
        if digest(input_path) != input_hash:
            raise ValueError("Public GLRT input changed during inference")
        receipts = [json.loads(p.read_text()) for p in (output / "read_receipts").glob("*.json")]
        roots = {s["process_id"] for s in terminal["stages"]}
        observed = {r["pid"] for r in receipts}
        expected = len(roots) + sum(len(r["python_spawns"]) for r in receipts)
        if (not roots <= observed or len(receipts) != expected or len(observed) != expected
                or any(r["denied_paths"] for r in receipts)
                or any(r["parent_pid"] not in observed | {os.getpid()} for r in receipts)):
            raise ValueError("Missing or denied per-process read audit")
        terminal["read_audit"] = dict(receipts=len(receipts), denied_paths=[],
                                      all_launched_processes_accounted=True,
                                      historical_result_or_GPS_reads=False)
        validate_terminal(terminal, input_sha256=input_hash)
    except (Exception, Deadline) as error:
        terminal.update(state="failed", position=None, reason=str(error), error_type=type(error).__name__)
    finally:
        terminal["elapsed_seconds"] = time.monotonic() - began
        persist(output / "terminal.json", terminal)
    print(json.dumps({k: terminal.get(k) for k in ("state", "model_version", "position", "reason", "elapsed_seconds")}), flush=True)
    return terminal


def revision():
    path = ROOT / "release-revision.txt"
    return path.read_text().strip() if path.exists() else "development"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--maximum-seconds", type=int, default=1200)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.root, args.case, args.tle_root)
    else:
        if args.input is None or args.output is None:
            parser.error("--input and --output required")
        result = run(args.input, args.output, maximum_seconds=args.maximum_seconds, tle_root=args.tle_root)
        raise SystemExit(1 if result["state"] == "failed" else 0)
