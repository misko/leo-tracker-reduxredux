"""Prepare one manifest-selected ALGO02 scan through read-only public ports.

Separate read-only subprocesses export existing GLRT products and inspect the
private TLE archive. Elevated access is required by their filesystem permissions.
Neither stage reads position truth or any previous localization result.
"""

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SOURCE = Path("/home/mouse9911/gits/leo-shared-production-main/src")


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def member(run_dir, case):
    matches = [r for r in read(run_dir / "sample.json")["selected"]
               if r["dataset_label"] == case]
    if len(matches) != 1 or Path(case).name != case:
        raise ValueError("case must be a unique sealed manifest member")
    return matches[0]


def validate_export(run_dir, case):
    entry = member(run_dir, case)
    receipt = read(run_dir / case / "input_receipt.json")
    if receipt["recording_id"] != entry["recording_id"]:
        raise ValueError("export belongs to another recording")
    if receipt["sample_sha256"] != sha(run_dir / "sample.json"):
        raise ValueError("sealed cohort membership changed")
    if receipt["raw_authority_digest"] != entry["raw_authority_digest"]:
        raise ValueError("raw authority changed")
    if receipt["status"] == "exported":
        if sha(run_dir / case / "tracking.json") != receipt["tracking_sha256"]:
            raise ValueError("frozen GLRT export changed")
    return receipt


def export(run_dir, case):
    entry = member(run_dir, case)
    directory = run_dir / case
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "input_receipt.json").exists():
        return validate_export(run_dir, case)
    began = time.monotonic()
    result = dict(case=case, recording_id=entry["recording_id"],
                  recording_format=entry["recording_format"],
                  sample_sha256=sha(run_dir / "sample.json"),
                  raw_authority_digest=entry["raw_authority_digest"],
                  GPS_or_localization_result_used=False,
                  existing_GLRT_only=True)
    try:
        if entry["recording_format"] == "short_window_iq_recording":
            sources = entry["tracking_inputs"]
            if not sources:
                raise ValueError("existing fast tracking contract unavailable")
            source = min(sources, key=lambda r: r["path"])
            payload = Path(source["path"]).read_bytes()
            if "sha256:" + hashlib.sha256(payload).hexdigest() != source["sha256"]:
                raise ValueError("frozen fast GLRT authority changed")
            (directory / "tracking.json").write_bytes(payload)
            result.update(adapter="fast_tracking_contract", source_path=source["path"],
                          source_sha256=source["sha256"])
        elif entry["recording_format"] == "starlink_adaptive_hop_iq":
            import leo.storage.scanner_tracking_source as public_port

            store = public_port.ScannerTrackingInputStore(
                Path("/srv/bulk/leo"), adaptive_probe_stride_ms=120)
            try:
                tracking = store.load(entry["recording_id"])
            finally:
                store.close()
            if tracking.session_id != entry["recording_id"]:
                raise ValueError("public GLRT port returned another recording")
            document = dataclasses.asdict(tracking)
            document["timing"] = (
                tracking.timing.model_dump(mode="json") if tracking.timing else None)
            write(directory / "tracking.json", document)
            result.update(adapter="ScannerTrackingInputStore.load",
                          public_adapter_path=public_port.__file__,
                          public_adapter_sha256=sha(public_port.__file__),
                          qualified=tracking.qualified)
        else:
            raise ValueError("unsupported recording format")
        result.update(status="exported", tracking_sha256=sha(directory / "tracking.json"))
    except (ValueError, OSError, RuntimeError) as error:
        result.update(status="input_unavailable", reason=f"{type(error).__name__}: {error}")
    result["seconds"] = time.monotonic() - began
    write(directory / "input_receipt.json", result)
    print(case, "export", result["status"], flush=True)
    return result


def restore_output_owner(run_dir, case):
    """Give only newly generated local analysis files to the cohort owner."""
    member(run_dir, case)
    if os.geteuid() != 0:
        return
    owner = run_dir.stat()
    for directory in (run_dir / case, run_dir / "causal_prior" / case):
        if directory.exists():
            for path in (directory, *directory.rglob("*")):
                if path.is_symlink():
                    raise ValueError("analysis output must not contain symlinks")
                os.chown(path, owner.st_uid, owner.st_gid)
    for name in (case + ".json", case + "_forecast.json"):
        path = run_dir / "causal_phase_history" / name
        if path.exists():
            os.chown(path, owner.st_uid, owner.st_gid)


def prepare(run_dir, case):
    import ds23_radio_noise as noise
    import evaluate_ds23_phase_refreshed as graph
    import export_ds23_causal_history as history
    import learn_ds23_causal_phase_forecast as forecast
    import prepare_ds23_genuine_causal_prior as prior

    source = validate_export(run_dir, case)
    directory = run_dir / case
    complete = directory / "preparation_receipt.json"
    if complete.exists():
        receipt = read(complete)
        for relative, digest in receipt["files_sha256"].items():
            if sha(run_dir / relative) != digest:
                raise ValueError("frozen prepared input changed: " + relative)
        return receipt
    began = time.monotonic()
    graph.OUTPUT = run_dir
    graph.prepare(case)
    prepared = read(directory / "prepared.json")
    if prepared["status"] == "prepared":
        noise.run(directory)
        prior.SOURCE, prior.OUTPUT = run_dir, run_dir / "causal_prior"
        prior.run(case)
        history.SOURCE = run_dir
        history_path = run_dir / "causal_phase_history" / (case + ".json")
        write(history_path, history.export(case))
        forecast.run(history_path)
    scientific_names = ("input_receipt.json", "tracking.json", "prepared.json",
                        "observations.json", "tracks.json", "radio_noise.json",
                        "bank.npz", "selected.tle", "previous.tle",
                        "previous_receipt.json", "receipt.json", "nominal_elements.json")
    paths = [directory / name for name in scientific_names if (directory / name).is_file()]
    paths += list((run_dir / "causal_prior" / case).glob("*.json"))
    paths += list((run_dir / "causal_prior" / case).glob("*.tle"))
    paths += list((run_dir / "causal_phase_history").glob(case + "*.json"))
    receipt = dict(case=case, status=prepared["status"],
                   seconds=time.monotonic() - began,
                   sample_sha256=sha(run_dir / "sample.json"),
                   tracking_sha256=source.get("tracking_sha256"),
                   files_sha256={str(p.relative_to(run_dir)): sha(p) for p in sorted(paths)},
                   code_sha256=sha(__file__), no_GPS_or_previous_results=True,
                   all_TLEs_causal=True, existing_GLRT_only=True,
                   history_window_hours=72)
    write(complete, receipt)
    print(case, "input preparation", receipt["status"], receipt["seconds"], flush=True)
    return receipt


def run(run_dir, case):
    entry = member(run_dir, case)
    (run_dir / case).mkdir(parents=True, exist_ok=True)
    (run_dir / "causal_prior").mkdir(exist_ok=True)
    (run_dir / "causal_phase_history").mkdir(exist_ok=True)
    # Public deployed adapter belongs to this repository's production checkout.
    # The legacy reference repositories are never on either PYTHONPATH.
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    env["PYTHONPATH"] = (
        str(PUBLIC_SOURCE) + ":tools"
        if entry["recording_format"] == "starlink_adaptive_hop_iq" else "src:tools")
    base = [str(ROOT / ".venv/bin/python"), str(Path(__file__).resolve()),
            "--case", case, "--run-dir", str(run_dir)]
    export_command = base + ["--stage", "export"]
    if os.geteuid() != 0:
        export_command = ["sudo", "-n", "env", "PYTHONPATH=" + env["PYTHONPATH"],
                          "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1", *export_command]
    subprocess.run(export_command, cwd=ROOT, env=env,
                   check=True, timeout=180)
    env["PYTHONPATH"] = "src:tools"
    command = base + ["--stage", "prepare"]
    if os.geteuid() != 0:
        command = ["sudo", "-n", "env", "PYTHONPATH=src:tools",
                   "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1", *command]
    subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", "export", "prepare"), default="all")
    args = parser.parse_args()
    target = args.run_dir.resolve()
    if target.is_relative_to(Path("/mnt/qnap01")):
        parser.error("analysis outputs must be outside the read-only QNAP corpus")
    member(target, args.case)
    if args.stage == "all":
        run(target, args.case)
    elif args.stage == "export":
        export(target, args.case)
    else:
        try:
            prepare(target, args.case)
        finally:
            restore_output_owner(target, args.case)
