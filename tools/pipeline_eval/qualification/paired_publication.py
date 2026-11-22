"""Time one matched, single-core raw-I/Q-to-publication pair on Gauss."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import subprocess
import time

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.storage.fast_scan import FastScanStore, immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
BASELINE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/run")


def child_cpu():
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def evidence(root, receipt, started_ns):
    run = receipt["run_id"]
    scans = FastScanStore(root)
    publication = FastStandardAnalysisStore(root)
    detail = publication.detail(run)
    terminal_path = scans.automatic_workspace(run) / "terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    if canonical_digest(terminal) != receipt["terminal_sha256"] or detail["terminal_sha256"] != receipt["terminal_sha256"]:
        raise ValueError("Terminal receipt failed digest verification")
    report = scans.detail(run, include_points=False)
    if (report["session_id"] != receipt["session_id"] or detail["state"] != receipt["decision"]
            or detail["region"] != receipt["region"] or detail.get("evaluation_reference") is not None):
        raise ValueError("Published recording, region or decision differs from the timed invocation")
    state = detail["state"]
    names = [p["name"] for p in detail["artifacts"]]
    science = {}
    if state == "complete":
        path, grid = publication.position_path(run), publication.position_grid(run)
        if names != list(PLOTS) or path is None or grid is None:
            raise ValueError("Completed fix has incomplete evidence")
        for name, document in (("path", path), ("grid", grid)):
            if (document["region_center"] != receipt["region"]["center"]
                    or document["box_width_km"] != receipt["region"]["width_km"]):
                raise ValueError("Published position evidence uses a different search region")
            # The binding includes the build-specific detector and terminal digests.
            science[name] = canonical_digest({k: v for k, v in document.items()
                                               if k not in ("binding", "elapsed_seconds")})
        for p in detail["artifacts"]:
            publication.artifact(run, p["name"], p["sha256"])
    elif state != "withheld" or names or not terminal.get("reason"):
        raise ValueError("Invalid terminal state")
    return dict(receipt=receipt, raw_authority=detail["raw_authority"], arms=terminal["arms"],
                owners={a: x["owner_sha256"] for a, x in detail["arms"].items()},
                reason=terminal.get("reason"), artifacts=detail["artifacts"], scientific_digests=science,
                terminal_file_s=(terminal_path.stat().st_mtime_ns-started_ns)/1e9)


def measure(launcher, root, args, specification=None):
    root.mkdir()  # Every arm starts without a detection, solver or publication cache.
    env = os.environ | dict(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE"):
        env.pop(key, None)
    env.pop("ALGO08_EXPERIMENT_CONFIG", None)
    if specification is not None:
        env["ALGO08_EXPERIMENT_CONFIG"] = str(specification.resolve())
    command = [str(launcher.resolve()), "--recording", str(args.recording.resolve()),
               "--region", str(args.region.resolve()), "--archive", str(args.archive.resolve()),
               "--bulk-root", str(root.resolve())]
    start_ns = time.time_ns()
    before_cpu, before_wall = child_cpu(), time.monotonic()
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=args.timeout)
    wall, cpu = time.monotonic()-before_wall, child_cpu()-before_cpu
    if result.returncode:
        raise RuntimeError(f"Launcher exited {result.returncode}: {result.stderr[-1500:]}")
    summary = evidence(root, json.loads(result.stdout.splitlines()[-1]), start_ns)
    return dict(launcher=command[0], elapsed_s=wall, cpu_s=cpu, **summary)


def run_pair(args):
    if args.cpu not in os.sched_getaffinity(0):
        raise ValueError("Selected CPU is outside the scheduling affinity")
    os.sched_setaffinity(0, {args.cpu})
    os.setpriority(os.PRIO_PROCESS, 0, max(15, os.getpriority(os.PRIO_PROCESS, 0)))
    subprocess.run(["ionice", "-c2", "-n7", "-p", str(os.getpid())], check=True)
    LOCK.parent.mkdir(exist_ok=True)
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        args.output.mkdir(parents=True, exist_ok=False)
        runs = {}
        order = ("baseline", "candidate") if args.first == "baseline" else ("candidate", "baseline")
        result = dict(order=order, cpu=args.cpu, recording=str(args.recording.resolve()),
                      region=str(args.region.resolve()), runs=runs)
        pinned_config = None
        if args.candidate_config:
            spec = json.loads(args.candidate_config.read_bytes())
            result["candidate_specification"] = spec
            result["candidate_specification_digest"] = canonical_digest(spec)
            pinned_config = args.output/"candidate-config.json"
            immutable_json(pinned_config, spec)
        try:
            for name in order:
                runs[name] = measure(getattr(args, name), args.output/name, args,
                                     pinned_config if name == "candidate" else None)
            a, b = runs["baseline"], runs["candidate"]
            if a["raw_authority"] != b["raw_authority"] or any(
                    a["receipt"][k] != b["receipt"][k] for k in ("region","session_id","window_count")):
                raise ValueError("Pair used different waveform support or geography")
            result["elapsed_ratio"] = b["elapsed_s"]/a["elapsed_s"]
        except Exception as exc:
            result["failure"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            immutable_json(args.output/"pair.json", result)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "region", "archive", "candidate", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--baseline", type=Path, default=BASELINE)
    p.add_argument("--candidate-config", type=Path, help="Pinned experimental receiver and solver options")
    p.add_argument("--first", choices=("baseline","candidate"), required=True)
    p.add_argument("--cpu", type=int, default=2)
    p.add_argument("--timeout", type=int, default=1200)
    run_pair(p.parse_args())
