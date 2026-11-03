"""Freeze ALGO07 benchmark evidence and collect bounded Python stage profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import pstats
import resource
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def destination(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    return resolved


def write_new(path: Path, value: dict) -> None:
    path = destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def freeze(spec: Path, output: Path) -> dict:
    spec = spec.resolve()
    source = json.loads(spec.read_text())
    entries = source["files"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("A nonempty file inventory is required")
    rows = []
    seen = set()
    for entry in entries:
        path = (spec.parent / entry["path"]).resolve(strict=True)
        if path in seen:
            raise ValueError(f"Duplicate frozen path: {path}")
        seen.add(path)
        before = path.stat()
        actual = digest(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError(f"File changed while freezing: {path}")
        expected = entry.get("sha256", actual).removeprefix("sha256:")
        if actual != expected:
            raise ValueError(f"Source hash mismatch: {path}")
        rows.append(dict(entry, path=str(path), sha256=actual, bytes=after.st_size))
    if destination(output) in seen:
        raise ValueError("Manifest overlaps frozen evidence")
    result = dict(
        schema_version=1,
        kind="algo07-runtime-reference",
        created_utc_ns=time.time_ns(),
        specification_sha256=digest(spec),
        metadata=source.get("metadata", {}),
        files=rows,
    )
    write_new(output, result)
    return result


def verify(manifest: Path) -> dict:
    value = json.loads(manifest.read_text())
    if value.get("schema_version") != 1 or value.get("kind") != "algo07-runtime-reference":
        raise ValueError("Unsupported runtime reference")
    if not value.get("files"):
        raise ValueError("Empty runtime reference")
    failed = []
    seen = set()
    for row in value["files"]:
        path = Path(row["path"])
        if not path.is_absolute() or path in seen:
            raise ValueError("Reference paths must be absolute and unique")
        seen.add(path)
        try:
            good = path.stat().st_size == row["bytes"] and digest(path) == row["sha256"]
        except OSError:
            good = False
        if not good:
            failed.append(str(path))
    return dict(verified=not failed, files=len(seen), failed=failed)


def run(args: argparse.Namespace) -> dict:
    if not 0 < args.timeout <= 1800:
        raise ValueError("Stage timeout must be in (0, 1800] seconds")
    manifest_hash = digest(args.manifest)
    before = verify(args.manifest)
    if not before["verified"]:
        raise ValueError("Frozen benchmark evidence changed")
    output = destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    script = args.script.resolve(strict=True)
    tail = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    command = [sys.executable, "-B"]
    if not args.no_cprofile:
        command += ["-m", "cProfile", "-o", str(output / "profile.pstats")]
    command += [str(script), *tail]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        env.setdefault(key, "1")
    launch = dict(
        stage=args.stage,
        command=command,
        cwd=str(Path.cwd()),
        script_sha256=digest(script),
        manifest_sha256=manifest_hash,
        python=sys.version,
        executable=sys.executable,
        host=platform.node(),
        cpu_count=os.cpu_count(),
        load_average=list(os.getloadavg()),
        thread_settings={
            k: env[k] for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
        },
        cprofile_enabled=not args.no_cprofile,
        profiling_scope="named Python process only; child CPU is aggregated, child stacks are not",
    )
    write_new(output / "launch.json", launch)
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter()
    timed_out = False
    with (output / "worker.log").open("xb") as log:
        child = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True
        )
        try:
            code = child.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGTERM)
            with suppress(subprocess.TimeoutExpired):
                child.wait(timeout=2)
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            code = child.wait()
    elapsed = time.perf_counter() - started
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    after = verify(args.manifest)
    unchanged_manifest = digest(args.manifest) == manifest_hash
    result = dict(
        stage=args.stage,
        exit_code=code,
        timed_out=timed_out,
        wall_seconds=elapsed,
        user_cpu_seconds=usage_after.ru_utime - usage_before.ru_utime,
        system_cpu_seconds=usage_after.ru_stime - usage_before.ru_stime,
        peak_child_rss_kib=usage_after.ru_maxrss,
        reference_after=after,
        manifest_unchanged=unchanged_manifest,
        successful_execution=(
            code == 0 and not timed_out and after["verified"] and unchanged_manifest
        ),
        scientific_parity_checked=False,
    )
    write_new(output / "timing.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    f = commands.add_parser("freeze")
    f.add_argument("--spec", type=Path, required=True)
    f.add_argument("--output", type=Path, required=True)
    v = commands.add_parser("verify")
    v.add_argument("--manifest", type=Path, required=True)
    r = commands.add_parser("run")
    r.add_argument("--manifest", type=Path, required=True)
    r.add_argument("--stage", required=True)
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--timeout", type=float, required=True)
    r.add_argument("--script", type=Path, required=True)
    r.add_argument("--no-cprofile", action="store_true")
    r.add_argument("arguments", nargs=argparse.REMAINDER)
    s = commands.add_parser("show")
    s.add_argument("--profile", type=Path, required=True)
    s.add_argument("--limit", type=int, default=30)
    sample_parser = commands.add_parser("sample", help="Sample one live private research child")
    sample_parser.add_argument("--pid", type=int, required=True)
    sample_parser.add_argument("--research-root", type=Path, required=True)
    sample_parser.add_argument("--output", type=Path, required=True)
    sample_parser.add_argument("--duration", type=int, default=20)
    sample_parser.add_argument("--sampler", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "freeze":
            result = freeze(args.spec, args.output)
            print(json.dumps(dict(manifest=str(args.output), files=len(result["files"]))))
        elif args.operation == "verify":
            result = verify(args.manifest)
            print(json.dumps(result))
            if not result["verified"]:
                raise SystemExit(1)
        elif args.operation == "run":
            result = run(args)
            print(json.dumps(result))
            if not result["successful_execution"]:
                raise SystemExit(1)
        elif args.operation == "sample":
            from leo.cli.algo07_sample import sample

            result = sample(args)
            print(json.dumps(result))
            if not result['successful_sampling']:
                raise SystemExit(1)
        else:
            if args.limit < 1:
                raise ValueError("Positive profile row count required")
            pstats.Stats(str(args.profile)).strip_dirs().sort_stats("cumulative").print_stats(
                args.limit
            )
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"ALGO07 profile: {error}\n")


if __name__ == "__main__":
    main()
