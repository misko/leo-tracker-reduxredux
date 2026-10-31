"""Freeze whole-dataset membership and supervise bounded paired ALGO02/03 runs.

Geographic truth is deliberately absent from this execution adapter. Every
manifest member gets a receipt, including unavailable inputs and failed fits.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not replace:
        with path.open("x") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return
    temporary = path.with_suffix(".partial")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def member_rows(document):
    rows = document.get("members", document.get("selected"))
    if not isinstance(rows, list):
        raise ValueError("Dataset requires an explicit complete member list")
    return rows


def identities(member):
    return {member["recording_id"], member.get("session_id"),
            *member.get("session_ids", [])} - {None}


def historical_inputs(root):
    """Consume the earlier study's explicit sample-to-input mapping."""
    if root is None:
        return {}
    root = Path(root)
    result = {}
    for row in member_rows(read(root / "sample.json")):
        path = root / row["dataset_label"] / "tracking.json"
        if path.is_file():
            result[row["recording_id"]] = path
    return result


def freeze_dataset(args):
    manifest = read(args.manifest)
    old = historical_inputs(args.historical_root)
    public = read(args.public_map) if args.public_map else []
    supplemental = read(args.input_map) if args.input_map else None
    if supplemental and supplemental["dataset_manifest_sha256"] != digest(args.manifest):
        raise ValueError("Supplemental inputs belong to another dataset manifest")
    cases = []
    for index, member in enumerate(member_rows(manifest), 1):
        label = member.get("dataset_label", f"{args.dataset}-{index:04d}")
        if Path(label).name != label or not label.startswith(args.dataset + "-"):
            raise ValueError("Unsafe or wrong-dataset case label")
        matching = [p for p in public if p.get("session_id") in identities(member)]
        # A completed current-production analysis is preferable to a new fit.
        matching.sort(key=lambda p: (p.get("state") != "complete", p["job_id"]))
        selected = matching[0] if matching else None
        paths = ([Path(selected["input_path"])] if selected else [])
        supplied = [r for r in supplemental["rows"] if r.get("status") == "exported" and
                    (r.get("session_id") in identities(member) or r.get("case_id") == member.get("case_id"))] if supplemental else []
        paths.extend(Path(r["input_path"]) for r in supplied)
        if member["recording_id"] in old:
            paths.append(old[member["recording_id"]])
        paths.extend(Path(p["path"]) for p in member.get("tracking_inputs", []))
        input_record = None
        rejected = []
        for path in dict.fromkeys(paths):
            try:
                document = read(path)
                source = document.get("source", document)
                if source.get("session_id") not in identities(member):
                    raise ValueError("Tracking input belongs to another acquisition")
                supplied_hashes = [r["input_sha256"] for r in supplied if Path(r["input_path"]) == path]
                if supplied_hashes and digest(path) not in supplied_hashes:
                    raise ValueError("Supplemental public input changed")
                input_record = dict(path=str(path.resolve()), sha256=digest(path),
                                    session_id=source["session_id"],
                                    sample_rate_hz=source["sample_rate_hz"],
                                    public_schema="wrapped" if "source" in document else "bare")
                break
            except (OSError, ValueError, KeyError) as error:
                rejected.append(dict(path=str(path), reason=str(error)))
        cases.append(dict(dataset=args.dataset, case=label,
                          recording_id=member["recording_id"],
                          recording_format=member["recording_format"],
                          captured_utc_ns=member["captured_utc_ns"],
                          input=input_record, rejected_input_candidates=rejected,
                          production_job=(selected if selected and input_record and
                                          selected["input_path"] == input_record["path"] and
                                          selected.get("state") == "complete" else None),
                          raw_authority_digest=member.get("raw_authority_digest")))
    if len({c["case"] for c in cases}) != len(cases):
        raise ValueError("Duplicate dataset labels")
    if len({c["recording_id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate acquisitions in dataset denominator")
    document = dict(schema="algo03-whole-dataset-evaluation/v1", dataset=args.dataset,
                    manifest_path=str(args.manifest.resolve()), manifest_sha256=digest(args.manifest),
                    supplemental_input_map_sha256=digest(args.input_map) if args.input_map else None,
                    all_members_in_denominator=True, no_geographic_truth=True,
                    arms=["c0", "fitted_c"], matched_observations_candidates_priors_budgets=True,
                    member_count=len(cases), cases=cases)
    write(args.study / "datasets" / (args.dataset + ".json"), document)
    print(json.dumps(dict(dataset=args.dataset, members=len(cases),
                          inputs=sum(c["input"] is not None for c in cases),
                          reusable_production=sum(c["production_job"] is not None for c in cases))))


def freeze_runtime(args):
    """Copy executable sources once; verify bytes again before every launch."""
    destination = args.study / (args.runtime_name or ("runtime-" + args.kind))
    destination.mkdir(parents=True, exist_ok=False)
    files = {}
    folders = ["src", "tools", "deploy/config", "deploy/fast_graph_guard",
               "reports/ALGO03/releases/2026-10-30-r1"]
    sources = {p for folder in folders for p in (args.source_root / folder).rglob("*")}
    manifest = args.source_root / "reports/ALGO03/releases/2026-10-30-r1/manifest.json"
    frozen_science = read(manifest)["sha256"]
    sources.update(args.source_root / name for name in frozen_science)
    production_files = (read(args.production_root / "release-manifest.json")["files_sha256"]
                        if args.production_root else {})
    adapter_overlays = {"src/leo/storage/fast_graph_position.py", "tools/fast_graph_worker.py"}
    for source in sorted(sources):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        if source.is_symlink():
            raise ValueError("Runtime source may not contain symbolic links")
        relative = source.relative_to(args.source_root)
        if str(relative) in production_files and str(relative) not in adapter_overlays:
            source = args.production_root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(source)
        shutil.copyfile(source, target)
        if digest(source) != before or digest(target) != before:
            raise ValueError("Source changed while freezing: " + str(relative))
        files[str(relative)] = before
    for name, expected in (frozen_science.items() if args.kind == "candidate" else []):
        if digest(destination / name) != "sha256:" + expected.removeprefix("sha256:"):
            raise ValueError("Frozen scientific release differs: " + name)
    write(destination / "runtime-freeze.json", dict(
        source_root=str(args.source_root.resolve()), kind=args.kind,
        production_root=str(args.production_root) if args.production_root else None,
        adapter_overlays=sorted(adapter_overlays) if args.production_root else [],
        frozen_utc_ns=time.time_ns(), python=str(args.python.absolute()), files=files))
    print(json.dumps(dict(runtime=str(destination), files=len(files),
                          freeze_sha256=digest(destination / "runtime-freeze.json"))))


def verify_runtime(root):
    freeze = read(root / "runtime-freeze.json")
    for relative, expected in freeze["files"].items():
        if digest(root / relative) != expected:
            raise ValueError("Frozen executable changed: " + relative)
    return freeze


def bounded(command, log_path, timeout, *, cwd, environment):
    with log_path.open("xb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   cwd=cwd, env=environment, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
    return code, process.pid


def environment(root):
    return dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1",
                OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                PYTHONPATH=os.pathsep.join(map(str, (root / "src", root / "tools"))))


def baseline_one(case, study, root, python, maximum_seconds):
    folder = study / "cases" / case["case"]
    folder.mkdir(parents=True, exist_ok=True)
    receipt_path = folder / "baseline-receipt.json"
    if receipt_path.exists():
        return read(receipt_path)
    began = time.monotonic()
    receipt = dict(case=case["case"], dataset=case["dataset"], phase="baseline",
                   model_version="algo02-causal-family-v1", state="failed",
                   maximum_seconds=maximum_seconds,
                   runtime_freeze_sha256=digest(root / "runtime-freeze.json"))
    try:
        if case["input"] is None:
            receipt.update(state="unavailable", reason="no_existing_public_GLRT_input")
        elif case.get("production_job"):
            from leo.storage.fast_graph_position import FastGraphPositionStore
            store = FastGraphPositionStore("/srv/bulk/leo")
            job = store.status(case["production_job"]["job_id"])
            descriptor = store.export_analysis(job, folder / "algo03/snapshot")
            receipt.update(state="complete", reused_production=True,
                           descriptor_path=str(folder / "algo03/snapshot/descriptor.json"),
                           terminal=descriptor["terminal"])
        else:
            source = Path(case["input"]["path"])
            if digest(source) != case["input"]["sha256"]:
                raise ValueError("Frozen tracking input changed")
            command = [str(python), "-B", str(root / "tools/fast_graph_worker.py"),
                       "--input", str(source), "--output", str(folder / "algo02"),
                       "--maximum-seconds", str(maximum_seconds)]
            code, pid = bounded(command, folder / "baseline.log", maximum_seconds + 30,
                                cwd=root, environment=environment(root))
            terminal = read(folder / "algo02/terminal.json")
            receipt.update(state=terminal["state"], returncode=code, process_id=pid,
                           terminal=terminal, terminal_path=str(folder / "algo02/terminal.json"))
    except Exception as error:
        receipt.update(state="failed", reason=f"{type(error).__name__}: {error}")
    receipt["seconds"] = time.monotonic() - began
    write(receipt_path, receipt)
    return receipt


def candidate_one(case, study, root, python, maximum_seconds):
    folder = study / "cases" / case["case"]
    receipt_path = folder / "candidate-receipt.json"
    if receipt_path.exists():
        return read(receipt_path)
    began = time.monotonic()
    baseline = read(folder / "baseline-receipt.json")
    receipt = dict(case=case["case"], dataset=case["dataset"], phase="candidate",
                   state="failed", maximum_seconds=maximum_seconds,
                   runtime_freeze_sha256=digest(root / "runtime-freeze.json"))
    output = folder / "candidate-v2"
    try:
        if baseline["state"] != "complete":
            receipt.update(state="unavailable", decision="ALGO02_fallback",
                           reason="baseline_" + baseline["state"])
        else:
            if baseline.get("reused_production"):
                snapshot = Path(baseline["descriptor_path"])
                preparation_seconds = baseline["seconds"]
            else:
                from leo.storage.fast_graph_position import export_completed_worker_analysis
                export_began = time.monotonic()
                export_completed_worker_analysis(case["input"]["path"], folder / "algo02",
                                                 folder / "evaluation-export")
                preparation_seconds = time.monotonic() - export_began
                snapshot = folder / "evaluation-export/descriptor.json"
            descriptor = read(snapshot)
            if descriptor["terminal"] != baseline["terminal"]:
                raise ValueError("ALGO03 snapshot differs from paired ALGO02 comparator")
            command = [str(python), "-B", str(root / "tools/algo03_production_worker.py"),
                       "--snapshot", str(snapshot), "--preparation-seconds", str(preparation_seconds),
                       "--output", str(output), "--maximum-seconds", str(maximum_seconds)]
            code, pid = bounded(command, folder / "candidate-worker.log",
                                max(1, maximum_seconds - preparation_seconds + 30),
                                cwd=root, environment=environment(root))
            if code or not (output / "terminal.json").exists():
                raise ValueError("ALGO03 production wrapper failed; see retained worker log")
            from leo.contracts.fast_graph_position_v2 import validate_terminal
            terminal = validate_terminal(read(output / "terminal.json"),
                                         input_sha256=case["input"]["sha256"])
            if terminal["state"] != "complete":
                raise ValueError("ALGO03 production wrapper did not publish a complete result")
            if terminal["baseline"] != baseline["terminal"]:
                raise ValueError("Published ALGO03 envelope changed its ALGO02 comparator")
            receipt.update(state="complete", decision=terminal["decision"],
                           failure=terminal.get("failure"), read_audit=terminal.get("read_audit"),
                           terminal_path=str(output / "terminal.json"), process_id=pid,
                           preparation_seconds=preparation_seconds,
                           descriptor_sha256=digest(snapshot),
                           seconds=terminal["recovery_seconds"],
                           same_executable_as_deployment=True)
    except Exception as error:
        receipt.update(state="failed", decision="ALGO02_fallback",
                       reason=f"{type(error).__name__}: {error}")
    receipt["orchestration_wall_seconds"] = time.monotonic() - began
    receipt.setdefault("seconds", receipt["orchestration_wall_seconds"])
    write(receipt_path, receipt)
    return receipt


def run_cases(args):
    if not 1 <= args.workers <= 24 or not 1 <= args.maximum_seconds <= 1200:
        raise ValueError("Workers must be 1..24 and per-case cap 1..1200 seconds")
    phase = args.command
    root = args.runtime_root or args.study / ("runtime-" + phase)
    freeze = verify_runtime(root)
    cases = []
    for dataset in args.datasets:
        cases.extend(read(args.study / "datasets" / (dataset + ".json"))["cases"])
    amendment = args.study / "scope-amendment-fast-only.json"
    if amendment.exists():
        allowed = set(read(amendment)["members"])
        cases = [c for c in cases if c["case"] in allowed]
    if args.mode:
        cases = [c for c in cases if c["recording_format"] == args.mode]
    if args.cases:
        wanted = set(args.cases)
        cases = [c for c in cases if c["case"] in wanted]
        if {c["case"] for c in cases} != wanted:
            raise ValueError("Requested case outside selected dataset/mode")
    if args.exclude_cases:
        cases = [c for c in cases if c["case"] not in set(args.exclude_cases)]
    pending_baselines = 0
    if phase == "candidate":
        ready = [c for c in cases if (args.study / "cases" / c["case"] / "baseline-receipt.json").exists()]
        pending_baselines = len(cases) - len(ready)
        cases = ready
    receipts = []
    began = time.monotonic()
    def claimed(case):
        folder = args.study / "cases" / case["case"]
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / (phase + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return worker(case, args.study, root, Path(freeze["python"]), args.maximum_seconds)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        worker = baseline_one if phase == "baseline" else candidate_one
        futures = [pool.submit(claimed, case) for case in cases]
        for future in as_completed(futures):
            receipt = future.result()
            receipts.append(receipt)
            print(json.dumps({k: receipt.get(k) for k in ("case", "state", "seconds", "reason")}), flush=True)
            write(args.study / (phase + "-progress.json"), dict(
                total=len(cases), terminal=len(receipts), all_terminal=len(cases) == len(receipts),
                pending_baselines=pending_baselines,
                seconds=time.monotonic() - began,
                receipts=[{k: r.get(k) for k in ("case", "state", "seconds", "reason")} for r in receipts]),
                replace=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze-dataset")
    freeze.add_argument("--study", type=Path, required=True)
    freeze.add_argument("--dataset", required=True)
    freeze.add_argument("--manifest", type=Path, required=True)
    freeze.add_argument("--historical-root", type=Path)
    freeze.add_argument("--public-map", type=Path)
    freeze.add_argument("--input-map", type=Path)
    freeze.set_defaults(function=freeze_dataset)
    runtime = commands.add_parser("freeze-runtime")
    runtime.add_argument("--study", type=Path, required=True)
    runtime.add_argument("--kind", choices=("baseline", "candidate"), required=True)
    runtime.add_argument("--source-root", type=Path, required=True)
    runtime.add_argument("--python", type=Path, required=True)
    runtime.add_argument("--runtime-name")
    runtime.add_argument("--production-root", type=Path)
    runtime.set_defaults(function=freeze_runtime)
    for phase in ("baseline", "candidate"):
        run = commands.add_parser(phase)
        run.add_argument("--study", type=Path, required=True)
        run.add_argument("--datasets", nargs="+", required=True)
        run.add_argument("--workers", type=int, default=16)
        run.add_argument("--maximum-seconds", type=int, default=1200)
        run.add_argument("--mode", choices=("short_window_iq_recording", "starlink_adaptive_hop_iq"))
        run.add_argument("--cases", nargs="+")
        run.add_argument("--exclude-cases", nargs="+")
        run.add_argument("--runtime-root", type=Path)
        run.set_defaults(function=run_cases)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
