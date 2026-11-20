"""Run the lean GLRT-to-position receiver on explicitly supplied local files."""

import argparse
import hashlib
import importlib.util
import json
import math
import stat
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from resource import RLIMIT_AS, setrlimit
from time import perf_counter, process_time

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
ENTRY = HERE.relative_to(ROOT)
PREFIX = ENTRY.parent.parent
SOLVERS = ("joint", "smooth-clock")
ARMS = ("c0", "fitted_c")
BOUNDARY = "Complete local native GLRT factors through Graph and a supplied-region position fit"
LIMIT_MIB = 512
MAX_PROBES = 36_000
FILES = {"native": 64 * 1024**2, "catalogue": 4 * 1024**2, "track_config": 64 * 1024}
PACKAGES = (
    "numpy",
    "scipy",
    "sgp4",
    "pydantic",
    "pydantic_core",
    "annotated_types",
    "typing_extensions",
    "typing_inspection",
)
THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS")
SCIENCE = (
    "leo/__init__.py",
    "leo/analysis/__init__.py",
    "leo/analysis/graph_tracklets.py",
    "leo/analysis/polynomial_tracklets.py",
    "leo/analysis/tracklet_fitting.py",
    "leo/contracts/base.py",
    "leo/contracts/digests.py",
    "leo/contracts/sky.py",
    "leo/sky/frames.py",
    "leo/sky/propagation.py",
    "leo/sky/sampling.py",
    "reference/grid.py",
    "reference/native_archive.py",
    "variants/native_lean.py",
    "variants/projected_fit.py",
    "variants/robust_em.py",
    "variants/robust_orbit_fit.py",
    "variants/joint_orbits.py",
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def hex_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def failed(status, reason):
    return dict(
        result=dict(
            status=status,
            reason=reason,
            boundary=BOUNDARY,
            metrics={},
            arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
        )
    )


def closure(solver):
    if solver not in SOLVERS:
        raise ValueError(f"unsupported position solver: {solver}")
    names = SCIENCE + (("variants/joint_clock_model.py",) if solver == "smooth-clock" else ())
    yield ENTRY, HERE
    for name in names:
        if name.startswith("leo/"):
            staged = ROOT / name
            yield Path(name), staged if staged.is_file() else ROOT / "src" / name
        else:
            relative = PREFIX / name
            yield relative, ROOT / relative


def source_manifest(solver, output=None):
    records = {}
    for name, path in closure(solver):
        raw = path.read_bytes()
        records[str(name)] = dict(sha256=hex_sha(raw), lines=len(raw.splitlines()))
        if output is not None:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    return records


def capture_anchor(path):
    """Read the clock anchor for an input adapter, before the bounded full archive read."""
    with Path(path).open("rb") as stream:
        start = stream.read(64 * 1024).decode("ascii")
    prefix = '{"clock_anchor":'
    if not start.startswith(prefix):
        raise ValueError("expected a canonical complete native GLRT archive")
    anchor, _ = json.JSONDecoder().raw_decode(start, len(prefix))
    return (anchor["before"]["realtime_ns"] + anchor["after"]["realtime_ns"]) // 2


def interface(offer, capture, cutoff, catalogue_acquired, probe_limit):
    lat, lon = offer["center"]
    width = offer.get("width_km", 25.0)
    if (
        not isinstance(offer["id"], str)
        or not offer["id"].strip()
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
        or not math.isfinite(width)
        or width <= 2
    ):
        raise ValueError(
            "region needs an identifier, valid latitude/longitude, and width above 2 km"
        )
    if not all(
        type(t) is int and 0 < t < 9 * 10**18 for t in (capture, cutoff, catalogue_acquired)
    ):
        raise ValueError(
            "capture, cutoff, and catalogue acquisition must be positive UTC nanoseconds"
        )
    if not 0 < catalogue_acquired < cutoff <= capture <= cutoff + 1_000_000_000:
        raise ValueError("the catalogue must precede the cutoff and the capture clock bracket")
    if type(probe_limit) is not int or not 0 < probe_limit <= MAX_PROBES:
        raise ValueError(f"expected a positive probe ceiling at most {MAX_PROBES}")


def input_file(path, limit, expected=None):
    path = Path(path).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise ValueError(f"input requires a regular nonempty file at most {limit} bytes: {path}")
    if expected is None:
        with path.open("rb") as stream:
            expected = hashlib.file_digest(stream, "sha256").hexdigest()
    else:
        expected = expected.removeprefix("sha256:").lower()
        if len(expected) != 64 or len(bytes.fromhex(expected)) != 32:
            raise ValueError("expected a 32-byte SHA-256 input digest")
    return path, expected


def runtime_mounts():
    mounts, versions = {}, {}
    for name in PACKAGES:
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            raise ValueError(f"the receiver environment requires {name}")
        source = Path(spec.origin).resolve()
        if spec.submodule_search_locations:
            source = source.parent
        mounts[source] = f"/packages/{source.name}"
        shared = source.parent / f"{name}.libs"
        if shared.is_dir():
            mounts[shared] = f"/packages/{shared.name}"
        versions[name] = version(name)
    return mounts, versions


def sandbox(bundle, paths, solver, packages):
    interpreter = f"/python/bin/python{sys.version_info.major}.{sys.version_info.minor}"
    command = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        "/tmp",
        "--setenv",
        "PYTHONPATH",
        "/worker:/packages",
    ]
    for key in THREADS:
        command.extend(("--setenv", key, "1"))
    for path in ("/usr", "/lib", "/lib64"):
        if Path(path).is_dir():
            command.extend(("--ro-bind", path, path))
    mounts = {
        Path(sys.base_prefix): "/python",
        bundle: "/worker",
        **packages,
        **{path: f"/input/{key}" for key, path in paths.items()},
    }
    if len(set(paths.values())) != len(paths):
        raise ValueError("provide separate GLRT, catalogue, and track configuration files")
    for src, target in mounts.items():
        command.extend(("--ro-bind", str(src), target))
    return [*command, interpreter, "-B", "-S", f"/worker/{ENTRY}", "--worker", solver]


def solve(
    files,
    *,
    capture,
    cutoff,
    catalogue_acquired,
    offer,
    solver="joint",
    probe_limit=MAX_PROBES,
    expected=None,
    timeout=60,
):
    started = perf_counter()
    interface(offer, capture, cutoff, catalogue_acquired, probe_limit)
    if set(files) != FILES.keys() or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("three explicit input files and a positive finite deadline are required")
    expected = expected or {}
    paths, inputs = {}, {}
    for key, limit in FILES.items():
        path, digest = input_file(files[key], limit, expected.get(key))
        paths[key], inputs[key] = path, dict(path=f"/input/{key}", sha256=digest)
    request = dict(
        mode="native",
        cutoff=cutoff,
        catalog_timestamp=catalogue_acquired,
        offer=offer,
        probe_limit=probe_limit,
        **inputs,
    )
    parents, versions = runtime_mounts()
    with tempfile.TemporaryDirectory(prefix="lean-receiver-", dir="/tmp") as temp:
        bundle = Path(temp)
        source = source_manifest(solver, bundle)
        began = perf_counter()
        try:
            process = subprocess.run(
                sandbox(bundle, paths, solver, parents),
                input=encoded(dict(request=request, capture_utc_ns=capture)),
                capture_output=True,
                timeout=timeout,
                check=True,
            )
            out = json.loads(process.stdout)
        except subprocess.TimeoutExpired:
            out = failed("timed_out", f"sandbox exceeded {timeout:g} seconds")
        except (subprocess.CalledProcessError, OSError, ValueError) as exc:
            reason = (getattr(exc, "stderr", None) or b"").decode(errors="replace").strip()
            out = failed("failed", reason.splitlines()[-1] if reason else str(exc))
        worker_wall = perf_counter() - began
    return dict(
        **out,
        schema_version=1,
        solver=solver,
        offer=offer,
        input_sha256=hex_sha(encoded(request)),
        interface_sha256=hex_sha(
            encoded(dict(request=request, capture_utc_ns=capture, solver=solver))
        ),
        input_files_sha256={key: value["sha256"] for key, value in inputs.items()},
        source_sha256=hex_sha(encoded(source)),
        source_files=source,
        runtime_versions=versions,
        capture_utc_ns=capture,
        cutoff_utc_ns=cutoff,
        catalogue_acquired_utc_ns=catalogue_acquired,
        worker_wall_s=worker_wall,
        command_wall_s=perf_counter() - started,
    )


def worker(packet, solver):
    setrlimit(RLIMIT_AS, (LIMIT_MIB * 1024**2,) * 2)
    started = perf_counter(), process_time()
    request, capture = packet["request"], packet["capture_utc_ns"]
    if request["mode"] != "native" or any(request[key]["path"] != f"/input/{key}" for key in FILES):
        raise ValueError("the sandbox worker requires the three mounted native inputs")
    interface(
        request["offer"],
        capture,
        request["cutoff"],
        request["catalog_timestamp"],
        request["probe_limit"],
    )
    from tools.pipeline_eval.variants import native_lean, robust_orbit_fit

    if solver == "smooth-clock":
        from tools.pipeline_eval.variants import joint_clock_model as backend
    else:
        from tools.pipeline_eval.variants import joint_orbits as backend

    infer, extract = robust_orbit_fit.infer, native_lean.peak_lanes

    def checked_capture(*args):
        clock, lanes, counts = extract(*args)
        if clock["anchor_utc_ns"] != capture:
            raise ValueError("declared capture UTC differs from the native clock anchor")
        return clock, lanes, counts

    imported = native_lean._elapsed(started)
    try:
        robust_orbit_fit.infer, native_lean.peak_lanes = backend.infer, checked_capture
        out = native_lean.worker(request)
    finally:
        robust_orbit_fit.infer, native_lean.peak_lanes = infer, extract
    phases = out["stages"]
    phases["position_backend"] = phases.pop("same_exact_backend")
    phases["backend_import"] = {
        key: value + phases["backend_import"][key] for key, value in imported.items()
    }
    out["result"]["boundary"] = BOUNDARY
    out["worker"] = native_lean._elapsed(started)
    return out


def arguments(parser):
    for key in FILES:
        name = key.replace("_", "-")
        parser.add_argument(f"--{name}", type=Path, required=True)
        parser.add_argument(f"--{name}-sha256")
    for option in ("capture", "cutoff", "catalogue-acquired"):
        parser.add_argument(f"--{option}-utc-ns", type=int, required=True)
    parser.add_argument("--region", nargs=2, type=float, required=True, metavar=("LAT", "LON"))
    parser.add_argument("--region-id", default="supplied")
    parser.add_argument("--width-km", type=float, help="square region width, defaults to 25 km")
    parser.add_argument("--solver", choices=SOLVERS, default="joint")
    parser.add_argument("--probe-limit", type=int, default=MAX_PROBES)
    parser.add_argument("--timeout", type=float, default=60)


def run_cli(args):
    offer = dict(id=args.region_id, center=args.region)
    if args.width_km is not None:
        offer["width_km"] = args.width_km
    out = solve(
        {key: getattr(args, key) for key in FILES},
        expected={key: getattr(args, f"{key}_sha256") for key in FILES},
        capture=args.capture_utc_ns,
        cutoff=args.cutoff_utc_ns,
        catalogue_acquired=args.catalogue_acquired_utc_ns,
        offer=offer,
        solver=args.solver,
        probe_limit=args.probe_limit,
        timeout=args.timeout,
    )
    sys.stdout.buffer.write(encoded(out) + b"\n")
    return int(out["result"]["status"] in {"timed_out", "failed"})


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "--worker" and argv[1] in SOLVERS:
        sys.stdout.buffer.write(encoded(worker(json.load(sys.stdin), argv[1])) + b"\n")
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    arguments(commands.add_parser("solve", help="fit a local capture on one supplied region"))
    bundle = commands.add_parser("bundle", help="stage the exact deployment source closure")
    bundle.add_argument("--out", type=Path, required=True)
    bundle.add_argument("--solver", choices=SOLVERS, default="smooth-clock")
    args = parser.parse_args(argv)
    try:
        if args.command == "solve":
            return run_cli(args)
        target = args.out.resolve()
        if target.is_relative_to("/mnt/qnap01"):
            raise ValueError("the QNAP adapter is read-only")
        target.mkdir(parents=True, exist_ok=False)
        entries = source_manifest(args.solver, target)
        (target / "source-manifest.json").write_bytes(encoded(entries) + b"\n")
        print(target / ENTRY)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
