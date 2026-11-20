#!/usr/bin/env python3
"""Replay authenticated local native captures through a relocated wide compact receiver."""

import argparse
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import monotonic
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS")


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")


def checked(path, expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("a bare lowercase SHA-256 is required")
    if digest(path) != expected:
        raise ValueError(f"input or release digest differs: {path}")
    return path


def bindings(source):
    spec = read(source)
    if set(spec) != {"schema", "segments", "tle", "track_config", "offer", "screen_center"}:
        raise ValueError("explicit segment, TLE, track configuration and region keys are required")
    if spec["schema"] != "leo-portable-receiver-input/v1":
        raise ValueError("unknown saved-recording request schema")

    def resolved(item, keys):
        if set(item) != keys:
            raise ValueError("unexpected manifest asset keys")
        return (source.parent / item["path"]).resolve(strict=True)

    paths, edges, windows, formats = [], set(), 0, set()
    for item in spec["segments"]:
        path = resolved(item, {"path", "sha256"})
        metadata = read(checked(path, item["sha256"]))
        if path.name != "manifest.json" or (
            metadata["schema_version"],
            metadata["status"],
            metadata["sample_rate_hz"],
            metadata["window_ms"],
            metadata["receiver_ids"],
            metadata["sample_format"],
            metadata["sample_layout"],
        ) != (2, "complete", 10_000_000, 20, [0, 1], "ci16_le", "sample_receiver_iq"):
            raise ValueError("expected a complete schema-v2 dual-RX 10 MS/s CI16 segment")
        if metadata["session_id"] != path.parent.name or not 1 <= metadata["window_count"] <= 4096:
            raise ValueError("segment name or window count differs from its sealed capture")
        formats.add(json.dumps([metadata["configuration"], metadata["radio"]], sort_keys=True))
        edges.update(t["edge"] for t in metadata["configuration"]["targets"])
        windows += metadata["window_count"]
        paths.append(dict(path=str(path), sha256=item["sha256"], windows=metadata["window_count"]))
    if (
        not paths
        or len({row["path"] for row in paths}) != len(paths)
        or not 0 < windows <= 40000
        or len(formats) != 1
        or len(edges) != 1
        or not edges <= {"lower", "upper"}
    ):
        raise ValueError("the request needs one complete, bounded capture and one pilot edge")
    config = spec["track_config"]
    config_path = checked(resolved(config, {"path", "sha256"}), config["sha256"])
    history = spec["tle"]
    archive = resolved(history, {"path", "snapshots"})
    if not archive.is_dir() or not history["snapshots"]:
        raise ValueError("the original causal archive path and snapshot hashes are required")
    verify_history(archive, history["snapshots"])
    offer = spec["offer"]
    if set(offer) != {"center", "width_km"}:
        raise ValueError("the region offer requires a center and width in kilometers")
    entry = runpy.run_path(str(ROOT / "position/__main__.py"))
    entry["validate_region"](offer["center"], spec["screen_center"], offer["width_km"])
    return dict(
        segments=paths,
        count=windows,
        edge=edges.pop(),
        archive=str(archive),
        snapshots=history["snapshots"],
        config=str(config_path),
        config_sha256=config["sha256"],
        tile=offer["center"],
        width_km=offer["width_km"],
        screen_center=spec["screen_center"],
    )


def verify_history(archive, snapshots):
    found = {str(p.relative_to(archive)): p for p in archive.rglob("*.tle")}
    if set(found) != set(snapshots):
        raise ValueError("causal archive snapshot inventory differs from the manifest")
    for name, path in found.items():
        checked(path, snapshots[name])


def verify_package():
    lock = read(ROOT / "files.json")
    for name, sha in lock["files"].items():
        path = (ROOT / name).resolve(strict=True)
        if not path.is_relative_to(ROOT):
            raise ValueError("package asset escapes the portable release")
        checked(path, sha)
    return lock


def memory():
    status = dict(monotonic_s=monotonic(), rss_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss)
    unified = Path("/proc/self/cgroup")
    if not unified.is_file():
        return status
    record = next(
        (line[3:] for line in unified.read_text().splitlines() if line.startswith("0::")), None
    )
    if record is None:
        return status
    status["cgroup"] = record
    group = Path("/sys/fs/cgroup") / record.lstrip("/")
    for name in ("memory.max", "memory.peak", "memory.swap.max", "memory.swap.current"):
        path = group / name
        if path.is_file():
            value = path.read_text().strip()
            status[name] = int(value) if value.isdecimal() else value
    for file in ("cpu.stat", "memory.events"):
        path = group / file
        if path.is_file():
            status[file] = {k: int(v) for k, v in map(str.split, path.read_text().splitlines())}
    return status


def raw_bridge():
    sys.path.insert(0, str(ROOT / "capture"))
    import native_bridge

    return native_bridge


def verify_loaded(root):
    for name, module in tuple(sys.modules.items()):
        if name == "leo" or name.startswith("leo."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(root):
                raise RuntimeError(f"{name} came from outside the relocated package")


def raw_lane(job, lane):
    from time import process_time

    bridge = raw_bridge()
    from leo.storage import short_window

    previous = short_window.ShortWindowReader._member
    sizes = []

    def member(reader, name, size, sha):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return bridge.AuthenticatedMember(path, size, sha, sizes)
        return previous(reader, name, size, sha)

    os.sched_setaffinity(0, {job["cpus"][lane]})
    before, cpu = monotonic(), process_time()
    with patch.object(short_window.ShortWindowReader, "_member", member):
        bridge.stream_range(
            ROOT / "stock-wide.so", lane, job["segments"], "saved-recording", job["authority"]
        )
    verify_loaded(ROOT / "capture")
    save(
        Path(job["out"]) / f"raw-{lane}.json",
        dict(
            wall_s=monotonic() - before,
            cpu_s=process_time() - cpu,
            authenticated_chunks=len(sizes),
            compressed_bytes=sum(sizes),
            cpus=sorted(os.sched_getaffinity(0)),
        ),
    )


def positions(job):
    out = Path(job["out"])
    root = ROOT / "position"
    entry = runpy.run_path(str(root / "__main__.py"))
    entry["activate"](root)
    from leo.analysis.localization_v4 import native_bound

    from tools.pipeline_eval.variants import v5_direct_cavity

    verify_history(Path(job["archive"]), job["snapshots"])
    verify_package()
    binding = read(root / "native/manifest.json")
    rebound = out / "backend"
    rebound.mkdir()
    binary = rebound / "native_bound.so"
    binary.write_bytes((root / "native/native_bound.so").read_bytes())
    provider = native_bound.provider()[2]
    if any(value != provider[key] for key, value in binding["provider"].items() if key != "path"):
        raise ValueError("installed SciPy provider differs from the qualified packaged binary")
    binding.update(
        binary=str(binary),
        wrapper=str(root / "leo/analysis/localization_v4/native_bound.py"),
        source=str(root / "leo/analysis/localization_v4/native_bound.c"),
        provider=provider,
    )
    manifest = rebound / "manifest.json"
    save(manifest, binding)
    before = memory()
    result = v5_direct_cavity.run(
        native=str(out / "native.json"),
        native_sha256=job["native_sha256"],
        track_config=job["config"],
        config_sha256=job["config_sha256"],
        session=job["session"],
        archive=job["archive"],
        native_backend=manifest,
        library=root / "projector.so",
        tile=job["tile"],
        width_km=job["width_km"],
        screen_center=job["screen_center"],
    )
    entry["verify_project_modules"](root)
    verify_loaded(root)
    end = memory()
    save(out / "position.json", result)
    save(out / "position-resources.json", dict(start=before, end=end))
    print(json.dumps(result, allow_nan=False))


def replay(source, out, cpus, deadline):
    lock = verify_package()
    if len(set(cpus)) != 2 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose two distinct available CPUs")
    job = bindings(source)
    segments = job["segments"]
    if len(segments) < 2:
        raise ValueError("this two-lane entry requires at least two sealed segments")
    if (
        out.is_relative_to("/mnt/qnap01")
        or any(out.is_relative_to(Path(segment["path"]).parent.parent) for segment in segments)
        or out.is_relative_to(Path(job["archive"]))
    ):
        raise ValueError("choose a writable output outside the input capture and catalogue")
    out.mkdir(parents=True, exist_ok=False)
    begin = memory()
    bridge = raw_bridge()
    inventory = [
        dict(
            scope=f"segment-{index:08d}",
            path=str(Path(row["path"]).parent),
            manifest_digest="sha256:" + row["sha256"],
            windows=row["windows"],
        )
        for index, row in enumerate(segments)
    ]
    authority = bridge.inventory_digest(inventory, job["count"])
    capture = dict(
        edge=job["edge"],
        input_manifest_sha256=authority,
        segments_sha256=bridge.digest(segments),
        case=dict(id="saved-recording"),
    )
    job.update(
        authority=capture,
        cpus=cpus,
        out=str(out),
        session="fast-" + authority[7:39],
        request_sha256=digest(source),
        package_files_sha256=digest(ROOT / "files.json"),
        detector_sha256=lock["files"]["stock-wide.so"],
    )
    plan = out / "request.json"
    save(plan, job)
    try:
        with ExitStack() as stack:
            workers = []
            for lane in range(2):
                log = stack.enter_context((out / f"lane-{lane}.jsonl").open("wb"))
                worker = subprocess.Popen(
                    [sys.executable, "-IB", __file__, "_raw", str(plan), str(lane)], stdout=log
                )
                workers.append(worker)
            for worker in workers:
                remaining = deadline - (monotonic() - begin["monotonic_s"])
                if remaining <= 0 or worker.wait(timeout=remaining) != 0:
                    raise RuntimeError("authenticated raw worker did not complete")
    finally:
        for worker in locals().get("workers", ()):
            if worker.poll() is None:
                worker.kill()
                worker.wait()
    raw_end = memory()
    lanes = []
    for lane in range(2):
        with (out / f"lane-{lane}.jsonl").open() as fp:
            lanes.append([json.loads(line) for line in fp])
    doc, counts = bridge.native_document(
        dict(
            session_id=job["session"], recording=dict(segments=segments, window_count=job["count"])
        ),
        lanes,
        capture,
    )
    native = out / "native.json"
    bridge.save(native, doc)
    job["native_sha256"] = digest(native)
    save(plan, job)
    save(
        out / "raw-resources.json",
        dict(start=begin, raw_end=raw_end, handoff=memory(), counts=counts),
    )
    os.sched_setaffinity(0, {cpus[0]})
    os.execv(sys.executable, [sys.executable, "-IB", __file__, "_position", str(plan)])


def main():
    os.environ.update(dict.fromkeys(THREADS, "1"))
    if len(sys.argv) >= 3 and sys.argv[1] in ("_raw", "_position"):
        job = read(sys.argv[2])
        if sys.argv[1] == "_raw":
            raw_lane(job, int(sys.argv[3]))
        else:
            positions(job)
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cpus", type=int, nargs=2, default=sorted(os.sched_getaffinity(0))[:2])
    parser.add_argument("--raw-deadline", type=int, default=360)
    args = parser.parse_args()
    if not 1 <= args.raw_deadline <= 600:
        parser.error("raw deadline must be in 1–600 seconds")
    replay(args.manifest.resolve(strict=True), args.out.resolve(), args.cpus, args.raw_deadline)


if __name__ == "__main__":
    main()
