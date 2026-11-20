"""Bind the capture producer's folded anchor grid to x86 and a standalone Cortex-A9 ELF."""

import argparse
import ast
import gzip
import hashlib
import io
import json
import math
import os
import struct
import subprocess
import tarfile
from heapq import heapify, heappop
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import local_output, save_json
from .full_receiver_comparison import SCREEN
from .projector_arm import DEFAULT_CC

REPORT = SCREEN / "detector-origins/embedded"
FIXTURE = Path("/srv/bulk/leo-dev/cdol-20261119/folded-fixture/manifest.json")
HARNESS = Path(__file__).with_suffix(".c")
GRID = "_native_acquisition_grid.inc"
FLAGS = ("-std=c11", "-O3", "-ffp-contract=off", "-fno-fast-math", "-static")
ARM = ("-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard")
LIMIT = 90
DYPES = {
    "samples": "<c16",
    "template": "<c16",
    "frequencies": "<f8",
    "starts": "<i8",
    "stops": "<i8",
    "frame_offsets": "<i8",
    "prefix": "<f8",
    "scores": "<f8",
}
INPUT_ORDER = tuple(name for name in DYPES if name != "scores")
STAGES = (
    "input_and_validation",
    "workspace",
    "magnitude_preparation",
    "folded_grid_body",
    "score_output",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return digest(path.read_bytes())


def load_fixture(path):
    trust = json.loads(path.read_bytes())
    if trust["entry"] != "folded_anchor_score_grid" or set(trust["arrays"]) != set(DYPES):
        raise ValueError("unexpected capture-era kernel inputs")
    arrays = {}
    for key, dtype in DYPES.items():
        field = trust["arrays"][key]
        leaf = Path(field["path"])
        sizes = field["shape"]
        if leaf.name != field["path"] or field["dtype"] != dtype:
            raise ValueError(f"unexpected capture format for {key}")
        raw = (path.parent / leaf).read_bytes()
        if digest(raw) != field["sha256"]:
            raise ValueError(f"capture array digest mismatch: {key}")
        arrays[key] = np.frombuffer(raw, dtype).reshape(sizes)
    if arrays["prefix"].size != arrays["samples"].size + 1:
        raise ValueError("wrong captured power-prefix dimensions")
    if arrays["scores"].shape != (arrays["frequencies"].size, trust["epoch_count"]):
        raise ValueError("wrong captured output shape")
    sources = {}
    for filename, want in trust["source_files"].items():
        source = Path(filename)
        if not source.is_relative_to(Path(trust["producer"]["root"])) or file_sha(source) != want:
            raise ValueError("capture producer files differ from the export")
        sources[source.name] = source
    return trust, arrays, sources


def binary_fixture(arrays, sample_rate_hz, epochs):
    dimensions = (
        arrays["samples"].size,
        arrays["template"].size,
        arrays["frequencies"].size,
        arrays["starts"].size,
        arrays["frame_offsets"].size,
        epochs,
    )
    if arrays["starts"].shape != arrays["stops"].shape:
        raise ValueError("mismatched captured template intervals")
    packed = [struct.pack("<8s6Id", b"LEOFOLD1", *dimensions, sample_rate_hz)]
    for key in INPUT_ORDER:
        values = arrays[key]
        if values.dtype.kind == "i":
            if np.any(values < -(2**31)) or np.any(values >= 2**31):
                raise ValueError("captured indexes cannot be losslessly encoded as int32")
            values = values.astype("<i4")
        packed.append(values.tobytes())
    return b"".join(packed)


def fixture_tag(data):
    tag = 14695981039346656037
    for value in data:
        tag = ((tag ^ value) * 1099511628211) & (2**64 - 1)
    return f"{tag:016x}"


def note_elf(path, arm=False):
    binary = path.read_bytes()
    if binary[:4] != b"\x7fELF" or binary[4:6] != bytes((1 if arm else 2, 1)):
        raise ValueError("unexpected executable format")
    (machine,) = struct.unpack_from("<H", binary, 18)
    if machine != (40 if arm else 62):
        raise ValueError("unexpected executable machine")
    parsed = subprocess.check_output(
        ["readelf", "-h", "-l", "-A", str(path)], text=True, timeout=10
    )
    if "INTERP" in parsed or (
        arm
        and not all(
            tag in parsed
            for tag in ("hard-float ABI", "Tag_CPU_arch: v7", "Tag_Advanced_SIMD_arch")
        )
    ):
        raise ValueError("static Cortex-A9 hard-float build proof failed")
    return dict(bytes=len(binary), sha256=digest(binary), readelf=parsed)


def verify_clock(timing, *, tag, cells):
    want = ("CLOCK_MONOTONIC", "CLOCK_PROCESS_CPUTIME_ID")
    if (
        (timing["wall_clock"], timing["cpu_clock"]) != want
        or timing["cells"] != cells
        or timing["fixture_tag"] != tag
        or set(timing["stages"]) != set(STAGES)
        or timing["cpu_resolution_ns"] <= 0
        or timing["wall_resolution_ns"] <= 0
    ):
        raise ValueError("executed clock, grid, or fixture binding changed")
    for clock in ("wall_ns", "cpu_ns"):
        values = [v[clock] for v in timing["stages"].values()]
        if min(values) < 0 or sum(values) != timing["total"]["observed"][clock]:
            raise ValueError("stage clocks do not cover the observed interval exactly")
    if min(timing["stages"]["folded_grid_body"].values()) <= 0:
        raise ValueError("folded kernel body was not timed")


def compared(left, right, selector, freqs):
    def retained(scores):
        return selector(tuple(freqs), tuple(scores), 8, 5, 10_000.0, scores.shape[1])

    a, b = (np.asarray(retained(scores)) for scores in (left, right))
    error = float(np.max(np.abs(left - right)))
    agree = np.array_equal(a[:, 1:], b[:, 1:])
    if not (math.isfinite(error) and error <= 1e-10 and agree):
        raise ValueError("folded grid or capture producer's eight retained basins disagree")
    return dict(
        cells=left.size,
        max_absolute_score_delta=error,
        retained_epoch_cfo_exact=bool(agree),
        retained=b.tolist(),
    )


def archived_selector(path):
    selected = {"_local_peak_indexes", "_retain_score_map_peaks"}
    tree = ast.parse(path.read_bytes())
    keep = [node for node in tree.body if getattr(node, "name", None) in selected]
    if {node.name for node in keep} != selected:
        raise ValueError("capture producer uses another coarse selector")
    scope = dict(np=np, math=math, heapify=heapify, heappop=heappop)
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(path), "exec"), scope)
    return scope["_retain_score_map_peaks"]


def installed_portable(sources, arrays, rate, epochs):
    (binary,) = [path for name, path in sources.items() if name.endswith(".so")]
    module = spec_from_file_location("_native_acquisition", binary)
    native = module_from_spec(module)
    module.loader.exec_module(native)
    wall, cpu = perf_counter_ns(), process_time_ns()
    result = native.folded_anchor_score_grid_portable(
        *(arrays[name] for name in INPUT_ORDER), rate, epochs
    )
    return result, dict(wall_ns=perf_counter_ns() - wall, cpu_ns=process_time_ns() - cpu)


def package(path, files):
    with (
        path.open("xb") as target,
        gzip.GzipFile(fileobj=target, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, data in sorted(files.items()):
            records = tarfile.TarInfo(name)
            records.size = len(data)
            records.mode = 0o755 if name == "capture-board-folded" else 0o644
            archive.addfile(records, io.BytesIO(data))


def run(fixture, scratch, out):
    if os.sched_getaffinity(0) != {2}:
        raise ValueError("pin the whole qualification to its assigned host CPU 2")
    scratch.mkdir(exist_ok=False, parents=True)
    trust, arrays, sources = load_fixture(fixture)
    (scratch / GRID).write_bytes(sources[GRID].read_bytes())
    rate, epochs = trust["sample_rate_hz"], trust["epoch_count"]
    binary = binary_fixture(arrays, rate, epochs)
    path = scratch / "folded.input"
    path.write_bytes(binary)
    tag = fixture_tag(binary)
    targets = {
        "host": ("cc", (), ()),
        "arm": (str(DEFAULT_CC), ARM, ("qemu-arm", "-cpu", "cortex-a9")),
    }
    builds = {}
    for name, (cc, flags, prefix) in targets.items():
        executable = scratch / f"{name}-folded"
        command = [
            cc,
            *FLAGS,
            *flags,
            "-I",
            str(scratch),
            str(HARNESS),
            "-lm",
            "-o",
            str(executable),
        ]
        subprocess.run(command, check=True, timeout=30)
        compiler = subprocess.check_output([cc, "--version"], text=True, timeout=10)
        builds[name] = dict(
            command=command,
            compiler=compiler.splitlines()[0],
            **note_elf(executable, arm=bool(prefix)),
        )
    out.mkdir(exist_ok=True, parents=True)
    seal = dict(
        fixture=trust,
        fixture_manifest_sha256=file_sha(fixture),
        packed_input_sha256=digest(binary),
        packed_input_bytes=len(binary),
        packed_input_tag=tag,
        sources={
            p.name: file_sha(p)
            for p in (HARNESS, Path(__file__), sources[GRID], out / "PROTOCOL.md")
        },
        qemu=subprocess.check_output(["qemu-arm", "--version"], text=True).splitlines()[0],
        builds=builds,
    )
    save_json(out / "source-lock.json", seal)
    lock_sha = file_sha(out / "source-lock.json")
    selection = archived_selector(sources["acquisition.py"])
    reference, extension_timing = installed_portable(sources, arrays, rate, epochs)
    scores, records = {}, {}
    for name, (_, _, prefix) in targets.items():
        executable = scratch / f"{name}-folded"
        start = perf_counter_ns()
        proc = subprocess.run(
            [*prefix, str(executable), str(path)], check=True, capture_output=True, timeout=LIMIT
        )
        elapsed = perf_counter_ns() - start
        stats = json.loads(proc.stderr)
        score = np.frombuffer(proc.stdout, "<f8").reshape(reference.shape)
        verify_clock(stats, tag=tag, cells=score.size)
        records[name] = dict(
            timing=stats,
            external_elapsed_wall_ns=elapsed,
            score_sha256=digest(proc.stdout),
            vs_installed_portable=compared(reference, score, selection, arrays["frequencies"]),
        )
        scores[name] = score
        print(name, stats["stages"]["folded_grid_body"], flush=True)
    receipt = dict(
        source_lock_sha256=lock_sha,
        runs=records,
        host_vs_qemu=compared(scores["host"], scores["arm"], selection, arrays["frequencies"]),
        installed_portable_vs_capture_avx2=compared(
            arrays["scores"], reference, selection, arrays["frequencies"]
        ),
        host_installed_portable_timing=extension_timing,
        host_cpu=2,
        physical_pluto_run=False,
    )
    files = {"capture-board-folded": (scratch / "arm-folded").read_bytes(), "folded.input": binary}
    files["SHA256SUMS"] = "".join(f"{digest(v)}  {k}\n" for k, v in files.items()).encode()
    package(out / "cortex-a9-offline.tar.gz", files)
    receipt["target_distribution_sha256"] = file_sha(out / "cortex-a9-offline.tar.gz")
    save_json(out / "receipt.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    run(args.fixture, local_output(args.work), local_output(args.out))
