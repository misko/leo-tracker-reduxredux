"""Replay all saved IQ inside the memory-bound service and exec the position worker."""

import json
import os
import stat
import sys
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

BLOCK = 128 * 1024
MEMORY = 512 * 1024**2
CPUS = (18, 19)
LIMIT = 320
METHOD = "whole_memory_chain"
BOUNDARY = "Complete saved IQ through ordinary GLRT and row-major compact v5 in one capped service"


class AuthenticatedMember:
    """Send bounded compressed buffers and verify every byte before accepting a chunk."""

    def __init__(self, path, size, digest, verified):
        self.file = os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb")
        info = os.fstat(self.file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != size:
            self.file.close()
            raise ValueError("compressed chunk size or file type differs from its manifest")
        self.size, self.digest, self.verified = size, digest, verified
        self.hash = sha256()
        self.count = 0

    def read(self, size=BLOCK):
        data = self.file.read(min(BLOCK, size if size >= 0 else BLOCK))
        self.hash.update(data)
        self.count += len(data)
        return data

    def close(self):
        if self.file.closed:
            return
        try:
            while self.read():
                pass
            if self.count != self.size or "sha256:" + self.hash.hexdigest() != self.digest:
                raise ValueError("compressed chunk SHA-256 differs from its manifest")
            self.verified.append(self.count)
        finally:
            self.file.close()


def memory():
    member = Path("/proc/self/cgroup").read_text().splitlines()
    _, mode, group = member[0].split(":", 2)
    if len(member) != 1 or mode:
        raise ValueError("unified Linux cgroup membership required")
    path = Path("/sys/fs/cgroup") / group.lstrip("/")
    data = {
        key: int((path / key).read_text())
        for key in (
            "memory.current",
            "memory.peak",
            "memory.max",
            "memory.swap.max",
            "memory.swap.current",
        )
    }
    if data["memory.max"] != MEMORY or data["memory.swap.max"] != 0:
        raise ValueError("the current worker is outside the required 512 MiB zero-swap service")
    for filename, fields in (
        ("cpu.stat", ("usage_usec",)),
        ("memory.events", ("oom", "oom_kill", "max")),
        ("memory.stat", ("anon", "file", "kernel")),
    ):
        for line in (path / filename).read_text().splitlines():
            key, value = line.split()
            if key in fields:
                data[filename + "." + key] = int(value)
    return dict(
        data,
        cgroup=group,
        pid=os.getpid(),
        cpus=sorted(os.sched_getaffinity(0)),
        nice=os.getpriority(os.PRIO_PROCESS, 0),
        rss_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )


def mark(name):
    print("stage: " + name, flush=True)
    return dict(monotonic_s=perf_counter(), **memory())


def raw_lane():
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.storage import short_window
    from tools.pipeline_eval.qualification import recording_to_v5 as previous

    start, verified, timing = memory(), [], []
    member, analyze = short_window.ShortWindowReader._member, NativeShortWindow.analyze

    def stream(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    def timed(detector, *args, **kwargs):
        wall, cpu = perf_counter(), process_time()
        result = analyze(detector, *args, **kwargs)
        timing.append((perf_counter() - wall, process_time() - cpu))
        return result

    with (
        patch.object(short_window.ShortWindowReader, "_member", stream),
        patch.object(NativeShortWindow, "analyze", timed),
    ):
        previous.main()
    receipt = dict(
        start=start,
        end=memory(),
        compressed_chunks=len(verified),
        compressed_bytes=sum(verified),
        native_timings_s=timing,
    )
    print("whole-lane-result: " + previous.encoded(receipt), file=sys.stderr, flush=True)


def assemble(out, ident, deadline, detector):
    from tools.pipeline_eval.qualification import recording_to_v5 as previous
    from tools.pipeline_eval.qualification.full_v5_check import _load_case, _sha
    from tools.pipeline_eval.qualification.recovery_reads_trial import WORKER
    from tools.pipeline_eval.qualification.secant_end_to_end import capture_duration
    from tools.pipeline_eval.variants import orbit_projector, v5_lean

    start = mark("raw complete; assembly enter")
    if json.loads((out / "raw-worker-exits.json").read_bytes())["exit_codes"] != [0, 0]:
        raise ValueError("both saved-IQ detector lanes must complete")
    lanes, telemetry = [], []
    for lane in range(2):
        with (out / f"replayed-{lane}.jsonl").open() as stream:
            lanes.append(list(map(json.loads, stream)))
        log = (out / f"replayed-{lane}.log").read_text().splitlines()
        receipt = [
            json.loads(s.removeprefix("whole-lane-result: "))
            for s in log
            if s.startswith("whole-lane-result: ")
        ]
        if len(receipt) != 1 or any(
            receipt[0][b]["cgroup"] != start["cgroup"] or receipt[0][b]["cpus"] != [CPUS[lane]]
            for b in ("start", "end")
        ):
            raise ValueError("raw lane has no proof of CPU and cgroup membership")
        telemetry.append(receipt[0])
    case = _load_case(ident)
    capture = json.loads((out / "capture.json").read_bytes())
    document, counts = previous.native_document(case, lanes, capture, detector)
    native = out / "native.json"
    previous.save(native, document)
    duration = capture_duration(document)
    del document, lanes
    expected = json.loads((out.parent / "plan.json").read_bytes())["inputs"][ident]
    if _sha(native) != expected["native_sha256"] or duration <= 0:
        raise ValueError(
            "fresh native detector factors differ from the authenticated ordinary replay"
        )
    if sum(len(row["native_timings_s"]) for row in telemetry) != counts["processed_windows"]:
        raise ValueError("raw time inventory differs from the detector visit inventory")
    binding = previous.bind_request(case, native, out / "experiment.json")
    fit = out / "position"
    fit.mkdir()
    request = json.loads(Path(binding["request_path"]).read_bytes())
    request["job"]["output_root"] = str(fit)
    archived = json.loads(Path(expected["prior_request_path"]).read_bytes())
    for value in (request, archived):
        value["job"]["output_root"] = None
        value["job"]["native_input"]["path"] = None
    if request != archived or request["job"]["evaluation_reference"] is not None:
        raise ValueError("fresh fit does not carry the earlier truth-free scientific request")
    request["job"]["output_root"] = str(fit)
    request["job"]["native_input"]["path"] = str(native)
    previous.save(fit / "request.json", request)
    library = fit / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    previous.save(
        out / "raw-stages.json",
        dict(
            id=ident,
            raw_complete=start,
            assembly_complete=mark("assembly complete"),
            capture_seconds=duration,
            native_sha256=_sha(native),
            raw_counts=counts,
            raw_lanes=telemetry,
        ),
    )
    command = [str(v5_lean.PYTHON), "-B", str(Path(__file__)), "position", str(out), str(WORKER)]
    env = dict(
        os.environ,
        **previous.SINGLE_THREAD,
        PYTHONPATH=f"{v5_lean.SOURCE}:{v5_lean.RUNNER}:{previous.REPO}",
    )
    os.execve(command[0], command, env)


def position(out, worker_path):
    from tools.pipeline_eval.qualification import recording_to_v5 as previous
    from tools.pipeline_eval.qualification.recovery_reads_worker import worker

    if Path(worker.__code__.co_filename) != worker_path:
        raise ValueError("wrong row-major position worker")
    fit = out / "position"
    start = mark("position enter")
    worker(str(fit / "request.json"), str(fit / "result.json"), str(fit / "orbit_projector.so"))
    previous.save(out / "position-stages.json", dict(start=start, end=mark("position complete")))


def main():
    from tools.pipeline_eval.qualification import recording_to_v5 as previous

    if sys.argv[1] == "chain":
        out = Path(sys.argv[3])
        manifest = dict(start=mark("raw enter"), id=sys.argv[2])
        previous.save(out.parent / f"{sys.argv[2]}-begin.json", manifest)
        with patch.object(
            previous, "MODULE", "tools.pipeline_eval.qualification.whole_memory_chain_worker"
        ):
            previous.run_recording(sys.argv[2], out, CPUS, LIMIT, finish=assemble)
    elif sys.argv[1] == "position":
        position(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raw_lane()


if __name__ == "__main__":
    main()
