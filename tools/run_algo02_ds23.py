"""Freeze and supervise ALGO02 on every member of the sealed DS23 dataset.

This supervisor never sees the reference position. Each scan runs in its own
process with one BLAS thread; evaluation is a separate command.
"""

import argparse
import ast
import hashlib
import json
import importlib.metadata
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "reports/2026_10_19_algo02_ds23_full"
DATASET = ROOT / "reports/2026_10_18_ds23_post_ds22"
THREAD_ENV = {key: "1" for key in (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, document):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def source_closure(entries, root=ROOT):
    """Hash local absolute-import closure, including imports within functions."""
    todo = [Path(p) for p in entries]
    found = {}
    while todo:
        relative = todo.pop()
        if str(relative) in found:
            continue
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        found[str(relative)] = digest(path)
        tree = ast.parse(path.read_text(), filename=str(relative))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = relative.with_suffix("").parts[1:-1]
                    prefix = list(parts[:len(parts) - node.level + 1])
                    module_name = ".".join(prefix + ([node.module] if node.module else []))
                else:
                    module_name = node.module or ""
                if module_name:
                    names = [module_name]
                    names += [module_name + "." + alias.name for alias in node.names]
            for name in names:
                module = Path(*name.split("."))
                for base in (Path("tools"), Path("src")):
                    for candidate in (base / module.with_suffix(".py"), base / module / "__init__.py"):
                        if (root / candidate).is_file():
                            todo.append(candidate)
    return dict(sorted(found.items()))


def compact_members(manifest):
    rows = []
    for member in sorted(manifest["members"], key=lambda row: row["dataset_label"]):
        row = {key: member[key] for key in (
            "dataset_label", "recording_id", "recording_format", "case_id",
            "captured_utc_ns", "tracking_inputs")}
        row["raw_authority_digest"] = member["raw_recording"]["identity_sha256"]
        rows.append(row)
    if len({row["dataset_label"] for row in rows}) != len(rows):
        raise ValueError("duplicate dataset labels")
    if len({row["recording_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate recording identities")
    return rows


def seal(run_dir, workers=30, timeout=1200):
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "protocol.json").exists():
        raise FileExistsError("ALGO02 freeze already exists; use run to resume")
    authority = DATASET / "manifest.json"
    authority_sha = digest(authority)
    if (DATASET / "manifest.sha256").read_text().split()[0] != "sha256:" + authority_sha:
        raise ValueError("DS23 manifest authority mismatch")
    members = compact_members(read(authority))
    development = read(ROOT / "reports/2026_10_18_algo01_ds23_random20/sample.json")
    old_cases = {row["dataset_label"] for row in development["selected"]}
    sample = dict(dataset_id="DS23", algorithm="ALGO02-v1", population=len(members),
        sample_size=len(members), selected=members, manifest_sha256="sha256:" + authority_sha,
        selection="all sealed members, without readiness or outcome filtering",
        original_regional_center=[37.906, -122.545], box_width_km=25,
        development_cases=sorted(old_cases), GPS_used_for_sampling_or_inference=False)
    write(run_dir / "sample.json", sample)
    entries = ["tools/run_algo02_ds23.py", "tools/prepare_algo02_ds23.py", "tools/algo02_scan.py"]
    protocol = dict(algorithm="ALGO02-v1", frozen_utc=datetime.now(timezone.utc).isoformat(),
        dataset_manifest_sha256=authority_sha, sample_sha256=digest(run_dir / "sample.json"),
        workers=workers, available_logical_cpus=os.cpu_count(),
        available_affinity_cpus=len(os.sched_getaffinity(0)), case_timeout_s=timeout,
        source_sha256=source_closure(entries), thread_environment=THREAD_ENV,
        python_version=sys.version,
        package_versions={name: importlib.metadata.version(name) for name in ("numpy", "sgp4", "pydantic")},
        configuration=dict(regional_center=[37.906, -122.545], box_width_km=25,
            initial_position_east_north_km=[0, 0], receiver_support_powers=[1., .6, .2],
            fragment_bias_sigma_hz=300., causal_history_hours=72,
            phase_prior="qualified causal history mean_and_distribution",
            linear_policy="all_linear", minimum_linear_points=6,
            new_linear_noise_variance_multiple=2., linear_bias_sigma_hz=300.,
            phase_rounds=5, position_steps=48, maximum_paired_gate_rounds=4,
            linear_phase_convergence_s=.01, paired_c_arms=["c0", "fitted_c"],
            linear_failure_policy="fallback to the qualified curved pair",
            calibration_from_curved_only=True, shared_linear_calibration_covariance=True,
            cross_scan_position_pooling=False, postscan_TLE=False, refined_IQ=False,
            statistical_gate_relaxation=False, reference_GPS_in_inference=False),
        inference_entrypoints=entries[1:],
        denominator_policy="retain every recording; never silently substitute a missing position",
        evidence_reuse="verified observation/preparation inputs only; fresh inference for every scan")
    write(run_dir / "protocol.json", protocol)
    print(json.dumps(dict(status="sealed", population=len(members), workers=workers,
        protocol_sha256=digest(run_dir / "protocol.json"))), flush=True)


def verify_freeze(run_dir):
    protocol = read(run_dir / "protocol.json")
    if digest(run_dir / "sample.json") != protocol["sample_sha256"]:
        raise ValueError("sealed membership changed")
    changed = [name for name, expected in protocol["source_sha256"].items()
               if digest(ROOT / name) != expected]
    if changed:
        raise ValueError("frozen source changed: " + ", ".join(changed))
    return protocol


def bounded_command(command, stream, seconds, env):
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=stream,
                               start_new_session=True)
    try:
        return process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        # Preparation may have read-only archive children under sudo. Terminate
        # this newly created process group, including those elevated children.
        privileged = subprocess.run(["sudo", "-n", "kill", "-TERM", "--", "-" + str(process.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if not privileged:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            subprocess.run(["sudo", "-n", "kill", "-KILL", "--", "-" + str(process.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        return 124


def worker(case, run_dir, protocol):
    began = time.monotonic()
    directory = run_dir / case
    directory.mkdir(exist_ok=True)
    receipt_path = directory / "execution_receipt.json"
    protocol_sha = digest(run_dir / "protocol.json")
    if receipt_path.exists():
        receipt = read(receipt_path)
        if receipt["protocol_sha256"] != protocol_sha:
            raise ValueError("case receipt belongs to a different freeze")
        result = directory / "algo02_result.json"
        if receipt.get("result_sha256") and digest(result) != receipt["result_sha256"]:
            raise ValueError("completed scientific result changed")
        return receipt
    verify_freeze(run_dir)
    env = dict(os.environ, PYTHONPATH="src:tools", PYTHONHASHSEED="0", **THREAD_ENV)
    stages = []
    with (directory / "pipeline.log").open("a") as stream:
        for script in ("prepare_algo02_ds23.py", "algo02_scan.py"):
            elapsed = time.monotonic() - began
            remaining = max(1, protocol["case_timeout_s"] - elapsed)
            command = [str(ROOT / ".venv/bin/python"), str(ROOT / "tools" / script),
                       "--case", case, "--run-dir", str(run_dir), "--stage", "all"]
            code = bounded_command(command, stream, remaining, env)
            stages.append(dict(script=script, code=code, seconds=time.monotonic() - began))
            if code:
                break
    result_path = directory / "algo02_result.json"
    receipt = dict(case=case, protocol_sha256=protocol_sha, stages=stages,
        code=stages[-1]["code"], seconds=time.monotonic() - began,
        result_sha256=digest(result_path) if result_path.exists() else None)
    write(receipt_path, receipt)
    return receipt


def run(run_dir):
    protocol = verify_freeze(run_dir)
    cases = [row["dataset_label"] for row in read(run_dir / "sample.json")["selected"]]
    receipts = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=protocol["workers"]) as pool:
        futures = {pool.submit(worker, case, run_dir, protocol): case for case in cases}
        for future in as_completed(futures):
            case = futures[future]
            try:
                receipt = future.result()
            except Exception as error:
                receipt = dict(case=case, code=1, supervisor_error=repr(error))
            receipts.append(receipt)
            write(run_dir / "execution.json", dict(receipts=receipts, completed=len(receipts),
                total=len(cases), elapsed_s=time.monotonic() - started,
                all_terminal=len(receipts) == len(cases)))
            print(json.dumps(dict(completed=len(receipts), total=len(cases), **receipt)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--stage", choices=("seal", "run", "verify"), required=True)
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--case-timeout", type=int, default=1200)
    args = parser.parse_args()
    if args.workers < 1 or args.case_timeout <= 0:
        parser.error("positive worker count and timeout required")
    if args.stage == "seal":
        seal(args.run_dir, args.workers, args.case_timeout)
    elif args.stage == "run":
        run(args.run_dir)
    else:
        verify_freeze(args.run_dir)
        print("freeze verified")
