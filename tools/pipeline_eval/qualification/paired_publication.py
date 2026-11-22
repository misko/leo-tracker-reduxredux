"""Time one matched, single-core raw-I/Q-to-publication pair on Gauss."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import time

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.fast_scan import FastScanStore, immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification import cache_residency


LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
BASELINE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/run")


def verify_sources(launcher, sources):
    """Resolve the manifest relative to the measured launcher, including itself."""
    launcher = launcher.resolve(strict=True)
    entries = {Path(name): digest for name, digest in sources.items()}
    if not entries or any(p.is_absolute() or ".." in p.parts for p in entries):
        raise ValueError("Expected source pins relative to the research checkout")
    roots = [root for root in launcher.parents if launcher.relative_to(root) in entries]
    if len(roots) != 1:
        raise ValueError("Candidate source manifest must identify its launcher")
    for name, expected in entries.items():
        actual = hashlib.sha256((roots[0] / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Candidate source changed: {name}")


def archive_identity(path):
    root = path.resolve(strict=True)
    snapshots = {ref.path.name: ref.sha256 for ref in TleArchiveReader(root).list_snapshots("space-track")}
    return dict(root=str(root), snapshots_sha256=canonical_digest(snapshots))


def blind_assignment(panel_path, expected_sha256, recording, region, archive):
    panel_path = panel_path.resolve(strict=True)
    public = panel_path.parent
    private = public.parent / "scorer"
    if not private.is_dir() or os.access(private, os.R_OK) or os.access(private, os.X_OK):
        raise ValueError("Blind confirmation requires an inference account without scorer directory access")
    panel_bytes = panel_path.read_bytes()
    digest = hashlib.sha256(panel_bytes).hexdigest()
    if digest != expected_sha256:
        raise ValueError("Blind assignment manifest changed after freezing")
    panel = json.loads(panel_bytes)
    if not re.fullmatch(r"[0-9a-f]{64}", panel["commitment"]):
        raise ValueError("Invalid scoring-key commitment")
    recording, region = recording.resolve(strict=True), region.resolve(strict=True)
    job = {"recording": recording.name, "offer": region.stem}
    if (recording.parent != public or region.parent != public or region.suffix != ".json"
            or archive.resolve(strict=True) != public / "tle" or panel["jobs"].count(job) != 1):
        raise ValueError("Input pair does not belong to the frozen blind panel")
    inputs = panel["inputs"]
    orbit_names = sorted(p.relative_to(archive).as_posix() for p in archive.rglob("*.tle"))
    if (inputs["offers"][region.stem] != hashlib.sha256(region.read_bytes()).hexdigest()
            or inputs["recordings"][recording.name] != ShortWindowReader(recording).manifest_sha256
            or inputs["tle_objects"] != orbit_names):
        raise ValueError("Blind recording, region or orbital inventory changed after freezing")
    return dict(job=job, panel_sha256=digest, truth_commitment=panel["commitment"])


def child_usage():
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(cpu_s=usage.ru_utime + usage.ru_stime, input_blocks=usage.ru_inblock,
                output_blocks=usage.ru_oublock, major_faults=usage.ru_majflt,
                voluntary_switches=usage.ru_nvcsw, involuntary_switches=usage.ru_nivcsw)


def evidence(root, receipt, started_ns, *, read_only=False):
    run = receipt["run_id"]
    scans = FastScanStore(root)
    publication = FastStandardAnalysisStore(root)
    detail = publication.detail(run)
    workspace = scans.automatic_workspace(run, create=False) if read_only else scans.automatic_workspace(run)
    terminal_path = workspace / "terminal.json"
    terminal = json.loads(terminal_path.read_bytes())
    if canonical_digest(terminal) != receipt["terminal_sha256"] or detail["terminal_sha256"] != receipt["terminal_sha256"]:
        raise ValueError("Terminal receipt failed digest verification")
    if terminal.get("region") != receipt["region"]:
        raise ValueError("Terminal region differs from the timed invocation")
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


def measure(launcher, root, args, specification=None, *, before_launch=None):
    root.mkdir()  # Every arm starts without a detection, solver or publication cache.
    assigned_region = Algo08Region.parse(json.loads(args.region.read_bytes())).document()
    env = os.environ | dict(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE"):
        env.pop(key, None)
    env.pop("ALGO08_EXPERIMENT_CONFIG", None)
    if specification is not None:
        env["ALGO08_EXPERIMENT_CONFIG"] = str(specification.resolve())
    command = [str(launcher.resolve()), "--recording", str(args.recording.resolve()),
               "--region", str(args.region.resolve()), "--archive", str(args.archive.resolve()),
               "--bulk-root", str(root.resolve())]
    if before_launch is not None:
        before_launch()
    start_ns = time.time_ns()
    before, before_wall = child_usage(), time.monotonic()
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=args.timeout)
    wall = time.monotonic() - before_wall
    usage = {k: value - before[k] for k, value in child_usage().items()}
    if result.returncode:
        raise RuntimeError(f"Launcher exited {result.returncode}: {result.stderr[-1500:]}")
    receipt = json.loads(result.stdout.splitlines()[-1])
    if receipt.get("region") != assigned_region:
        raise ValueError("Launcher used a different region from the assigned offer")
    summary = evidence(root, receipt, start_ns)
    return dict(launcher=command[0], elapsed_s=wall, **usage, **summary)


@contextmanager
def single_core_slot(cpu):
    if cpu not in os.sched_getaffinity(0):
        raise ValueError("Selected CPU is outside the scheduling affinity")
    os.sched_setaffinity(0, {cpu})
    os.setpriority(os.PRIO_PROCESS, 0, max(15, os.getpriority(os.PRIO_PROCESS, 0)))
    subprocess.run(["ionice", "-c2", "-n7", "-p", str(os.getpid())], check=True)
    LOCK.parent.mkdir(exist_ok=True)
    # Shared readers use the same inode from separate inference accounts on Gauss.
    with LOCK.open("rb" if LOCK.exists() else "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def run_pair(args):
    with single_core_slot(args.cpu):
        args.output.mkdir(parents=True, exist_ok=False)
        runs = {}
        order = ("baseline", "candidate") if args.first == "baseline" else ("candidate", "baseline")
        result = dict(order=order, cpu=args.cpu, recording=str(args.recording.resolve()),
                      region=str(args.region.resolve()), runs=runs)
        pinned_config = None
        try:
            expected_archive = getattr(args, "archive_inventory_sha256", None)
            if expected_archive is not None:
                result["archive"] = archive_identity(args.archive)
                if result["archive"]["snapshots_sha256"] != expected_archive:
                    raise ValueError("Causal archive differs from the frozen assignment")
            if args.blind_panel:
                panel, digest = args.blind_panel
                result["blind_assignment"] = blind_assignment(Path(panel), digest, args.recording, args.region, args.archive)
            if args.candidate_config:
                spec = json.loads(args.candidate_config.read_bytes())
                result["candidate_specification"] = spec
                result["candidate_specification_digest"] = canonical_digest(spec)
                verify_sources(args.candidate, spec["sources"])
                pinned_config = args.output/"candidate-config.json"
                immutable_json(pinned_config, spec)
            cache_library = getattr(args, "cache_library", None)
            cache_arms = None
            if cache_library is not None:
                manifests = args.cache_manifests
                if not manifests:
                    raise ValueError("Cache observation requires assigned sealed manifest pins")
                query = cache_residency.load_query(cache_library.resolve(strict=True))
                page_size = os.sysconf("SC_PAGE_SIZE")
                store = FastScanStore(args.output)
                cache_arms = {}
                result["cache_observation"] = dict(
                    method="linux-cachestat", page_size_bytes=page_size,
                    manifests=cache_residency.manifest_pins(manifests), arms=cache_arms,
                )

                def observe(name):
                    cache_arms[name] = cache_residency.bound_snapshot(
                        store, args.recording, manifests, page_size, query,
                    )

            for name in order:
                measurement = (getattr(args, name), args.output/name, args,
                               pinned_config if name == "candidate" else None)
                if cache_arms is None:
                    runs[name] = measure(*measurement)
                else:
                    runs[name] = measure(*measurement, before_launch=lambda name=name: observe(name))
            a, b = runs["baseline"], runs["candidate"]
            if a["raw_authority"] != b["raw_authority"] or any(
                    a["receipt"][k] != b["receipt"][k] for k in ("region","session_id","window_count")):
                raise ValueError("Pair used different waveform support or geography")
            if expected_archive is not None and archive_identity(args.archive) != result["archive"]:
                raise ValueError("Causal archive changed during the pair")
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
    p.add_argument("--archive-inventory-sha256", help="Verify and record the assigned causal archive inventory")
    p.add_argument("--blind-panel", nargs=2, metavar=("MANIFEST", "SHA256"),
                   help="Verify an assigned opaque pair using a scorer-isolated account")
    p.add_argument("--first", choices=("baseline","candidate"), required=True)
    p.add_argument("--cpu", type=int, default=2)
    p.add_argument("--timeout", type=int, default=1200)
    run_pair(p.parse_args())
