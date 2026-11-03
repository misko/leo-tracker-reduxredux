"""Freeze public ALGO07 replay inputs and profile bounded, guarded numerical runs."""

import argparse
import importlib.util
import json
import os
import shutil
import time
from pathlib import Path

from leo.cli.algo07_profile import destination, digest, freeze, run, write_new

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "src/leo/analysis/research/joint_predictive_families.py"
EXCLUDED = {
    "candidate", "read_receipts", "matplotlib-cache", "launch.json",
    "worker.log", "read-audit.json", "decision.json",
}


def inventory(root):
    """Only original input files; never follow a link out of the public workspace."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] in EXCLUDED:
            continue
        if path.is_symlink():
            raise ValueError("Replay input contains a symbolic link")
        if path.is_file():
            result[str(relative)] = digest(path)
    return result


def snapshot(args):
    from algo06_cache import relocate

    from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6

    store = FastGraphPositionStoreV6(args.bulk_root)
    job = store.status(args.job)
    if not job or job["state"] != "complete":
        raise ValueError("Completed public ALGO07 job required")
    evidence = store.plot_evidence(job)
    source = Path(evidence["workspace"])
    if not (source / "history-bank.json").is_file():
        raise ValueError("Prepared ALGO07 replay workspace required")
    output = destination(args.output)
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Snapshot overlaps its production source")
    output.mkdir(parents=True, exist_ok=False)
    files = inventory(source)
    receipt = relocate(source, output / "input", source, files)
    if inventory(source) != files:
        raise ValueError("Public source changed during snapshot")
    _, after = store.terminal(job)
    if after != evidence["terminal_receipt"]:
        raise ValueError("Public terminal changed during snapshot")
    shutil.copyfile(KERNEL, output / "reference_kernel.py")
    write_new(output / "source.json", dict(
        job_id=args.job, run_id=job["run_id"], public_terminal=evidence["terminal_receipt"],
        relocation=receipt, kernel_sha256=digest(KERNEL),
        scope="Prepared ALGO07 numerical inputs; not raw IQ or a whole-pipeline replay",
    ))
    rows = [dict(path=str((output / "input" / name).resolve()), sha256=sha)
            for name, sha in receipt["relocated_hashes"].items()]
    rows.append(dict(path=str(output / "reference_kernel.py"), sha256=digest(KERNEL)))
    write_new(output / "spec.json", dict(files=rows, metadata=dict(job_id=args.job)))
    freeze(output / "spec.json", output / "frozen.json")
    print(json.dumps(dict(root=str(output), files=len(rows), job_id=args.job)))


def load_kernel(path):
    spec = importlib.util.spec_from_file_location("frozen_joint_kernel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.two_family_phase_evidence


def execute(args):
    import numpy as np

    from leo.analysis.research import joint_predictive_families as kernel

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    numerical = (
        load_kernel(args.kernel_file) if args.kernel_file else kernel.two_family_phase_evidence
    )
    calls = []

    def measured(*values, **keywords):
        number = len(calls)
        if args.mode == "capture" and number < 8:
            y, m, b, u, lp, v = values
            arrays = {"base_covariance": b}
            for label, group in (("observed", y), ("means", m), ("modes", u),
                                 ("log_priors", lp), ("visible", v)):
                arrays.update({f"{label}_{k}": a for k, a in enumerate(group)})
            np.savez(output / f"call-{number:02d}.npz", **arrays)
        began = time.perf_counter()
        result = numerical(*values, **keywords)
        calls.append(dict(seconds=time.perf_counter() - began,
                          observations=[len(a) for a in values[0]],
                          phases=[len(a) for a in values[1]]))
        if args.mode == "capture" and number < 8:
            from algo07_science.validation import clean
            write_new(output / f"call-{number:02d}.json", clean(result))
        return result

    # Install before importing modules which bind this function by name.
    kernel.two_family_phase_evidence = measured
    from algo07_history import collect_private
    from algo07_science import engine, runner
    from algo07_science.validation import clean

    root = args.input.resolve()
    began = time.perf_counter()
    if args.mode == "capture":
        engine.configure(root, output, collect_history=lambda request:
                         collect_private(root / "history-bank.json", request))
        d, z, checks = engine.load_case("SCAN")
        value = dict(checks=checks, family_count=len(d["families"]),
                     associated={a: len(z["baseline_owners"][a]) for a in engine.ARMS})
    else:
        write_new(output / "protocol.json", dict(
            settings=runner.SETTINGS, baselines={"SCAN": runner.published_baseline(root, "SCAN")}))
        value = runner.run_worker("SCAN", root, output)
    write_new(output / "summary.json", clean(dict(
        seconds=time.perf_counter() - began, kernel_seconds=sum(c["seconds"] for c in calls),
        kernel_calls=calls, result=value, kernel_sha256=digest(args.kernel_file or KERNEL),
        mode=args.mode, numerical_rerun=True, entire_pipeline_rerun=False,
    )))
    print(json.dumps(dict(mode=args.mode, calls=len(calls), seconds=time.perf_counter() - began)))


def receipt_tree(paths, supervisor_pid):
    """Separate concurrent trials' receipts by their actual process ancestry."""
    rows = {p: json.loads(p.read_text()) for p in paths}
    included = set()
    parents = {supervisor_pid}
    while True:
        new = {p for p, row in rows.items() if row["parent_pid"] in parents} - included
        if not new:
            break
        included.update(new)
        parents.update(rows[p]["pid"] for p in new)
    direct = [rows[p]["pid"] for p in included if rows[p]["parent_pid"] == supervisor_pid]
    return included, direct


def launch(args):
    from run_algo03_shadow import check_read_audit

    root = args.snapshot.resolve(strict=True)
    target = destination(args.output)
    if not target.is_relative_to(root) or target.is_relative_to(root / "input"):
        raise ValueError("Trial output must be new and inside snapshot, outside frozen input")
    provenance = json.loads((root / "source.json").read_text())
    if args.mode == "replay" and provenance.get("research_only"):
        raise ValueError("Research reconstruction lacks a production terminal for full replay")
    z = json.loads((root / "input/inputs/SCAN.json").read_text())
    env = dict(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MKL_NUM_THREADS="1", PYTHONPATH=os.pathsep.join(map(str, (
                   ROOT / "deploy/fast_graph_guard", ROOT / "src", ROOT / "tools"))),
               LEO_FAST_GRAPH_RUN_ROOT=str(root),
               LEO_FAST_GRAPH_INPUT=str(Path(z["native_path"]) / "tracking.json"),
               LEO_FAST_GRAPH_SOURCE_ROOT=str(ROOT),
               LEO_FAST_GRAPH_TLE_ROOT=str(root / "unused-archive"),
               MPLCONFIGDIR=str(target / "matplotlib-cache"))
    # Each process writes its own guard receipt. Older trial receipts are retained
    # but excluded when auditing this launch's process tree.
    existing = set((root / "read_receipts").glob("*.json"))
    arguments = ["execute", "--mode", args.mode, "--input", str(root / "input"),
                 "--output", str(target / "results")]
    if args.reference:
        arguments += ["--kernel-file", str(root / "reference_kernel.py")]
    previous = dict(os.environ)
    try:
        os.environ.update(env)
        result = run(argparse.Namespace(
            manifest=root / "frozen.json", output=target, script=Path(__file__),
            stage="algo07-" + args.mode, timeout=args.timeout,
            arguments=arguments, no_cprofile=args.no_cprofile,
        ))
    finally:
        os.environ.clear()
        os.environ.update(previous)
    current = set((root / "read_receipts").glob("*.json")) - existing
    owned, direct = receipt_tree(current, os.getpid())
    audit_root = target / "audit"
    (audit_root / "read_receipts").mkdir(parents=True)
    for path in owned:
        shutil.copyfile(path, audit_root / "read_receipts" / path.name)
    audit = check_read_audit(audit_root, direct[0] if len(direct) == 1 else -1)
    write_new(target / "read-audit.json", audit)
    print(json.dumps(dict(timing=result, audit=audit)))
    if not result["successful_execution"] or not audit["verified"]:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("snapshot")
    p.add_argument("--bulk-root", type=Path, required=True)
    p.add_argument("--job", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("run")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mode", choices=("capture", "replay"), required=True)
    p.add_argument("--reference", action="store_true")
    p.add_argument("--no-cprofile", action="store_true")
    p.add_argument("--timeout", type=float, default=1200)
    p = commands.add_parser("execute")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mode", choices=("capture", "replay"), required=True)
    p.add_argument("--kernel-file", type=Path)
    args = parser.parse_args()
    {"snapshot": snapshot, "run": launch, "execute": execute}[args.command](args)


if __name__ == "__main__":
    main()
