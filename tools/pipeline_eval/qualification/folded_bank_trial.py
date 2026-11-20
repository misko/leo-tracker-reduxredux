"""Compare the full FP64 folded FFT bank with the captured portable C grid."""

import argparse
import gzip
import io
import json
import os
import struct
import subprocess
import tarfile
from pathlib import Path
from statistics import median

import numpy as np

from ..__main__ import local_output, save_json
from . import capture_board_folded as capture

REPORT = capture.SCREEN / "acquisition-support/folded-bank"
KERNEL = Path(__file__).resolve().parents[1] / "variants/folded_bank.c"
SELECTED = ("captured", "weak-pair", "noise")
HOST_PASSES = 3
ARM_TIMEOUT = 70
SYSROOT = (
    Path(
        subprocess.check_output(
            [str(capture.DEFAULT_CC), "-print-sysroot"], text=True, timeout=10
        ).strip()
    )
    if __name__ == "__main__"
    else None
)


def synthetic(arrays, rate, epochs, planted):
    rng = np.random.default_rng(202611190121)
    n = arrays["samples"].size
    samples = (rng.normal(size=n) + 1j * rng.normal(size=n)).astype("<c16")
    recipe = None
    if planted:
        frame = arrays["template"]
        positions = np.arange(frame.size)
        component = [(713, 240_000, 0.22), (717, -240_000, 0.20)]
        scale = np.sqrt(np.mean(np.abs(frame) ** 2))
        for epoch, cfo, level in component:
            waveform = level * frame / scale * np.exp(2j * np.pi * positions * cfo / rate)
            for offset in arrays["frame_offsets"]:
                start = int(offset + epoch)
                take = min(frame.size, n - start)
                if take > 0:
                    samples[start : start + take] += waveform[:take]
        samples += 0.55 * np.exp(2j * np.pi * np.arange(n) * 400_000 / rate)
        recipe = dict(
            pilot_epochs_cfo_hz_rms=component,
            per_lane_noise_std=1,
            interfering_tone_hz_rms=[400_000, 0.55],
        )
    prefix = np.r_[0.0, np.cumsum(samples.real**2 + samples.imag**2)]
    data = dict(arrays, samples=samples, prefix=prefix)
    return capture.binary_fixture(data, rate, epochs), recipe


def executable(path, arm):
    raw = path.read_bytes()
    if raw[:6] != bytes((0x7F, 69, 76, 70, 1 if arm else 2, 1)) or struct.unpack_from(
        "<H", raw, 18
    )[0] != (40 if arm else 62):
        raise ValueError("wrong benchmark executable architecture")
    fields = subprocess.check_output(["readelf", "-h", "-d", "-A", path], text=True, timeout=10)
    if arm and not all(x in fields for x in ("hard-float ABI", "Tag_CPU_arch: v7", "NEON")):
        raise ValueError("Cortex-A9 hard-float executable required")
    return {"sha256": capture.digest(raw), "bytes": len(raw), "elf": fields}


def build(work, original, sysroot):
    flags = tuple(f for f in capture.FLAGS if f != "-static")
    if not (sysroot / "usr/include/fftw3.h").is_file():
        raise ValueError("matching ARM FFTW development headers required")
    machine = {
        "host": ("cc", ()),
        "arm": (str(capture.DEFAULT_CC), capture.ARM),
    }
    files = {}
    for method in ("direct", "bank"):
        here = work / method
        here.mkdir()
        include = here / capture.GRID
        include.write_bytes(original.read_bytes() if method == "direct" else KERNEL.read_bytes())
        for arch, (compiler, arch_flags) in machine.items():
            output = here / arch
            command = [compiler, *flags, *arch_flags, "-I", str(here), str(capture.HARNESS)]
            if method == "bank":
                command += ["-lfftw3"]
            command += ["-lm", "-o", str(output)]
            subprocess.run(command, check=True, timeout=30)
            files[f"{method}/{arch}"] = dict(command=command, **executable(output, arch == "arm"))
    return files


def attempt(program, prefix, input_path, tag, shape):
    run = subprocess.run(
        [*prefix, program, input_path],
        check=True,
        capture_output=True,
        timeout=ARM_TIMEOUT,
    )
    lines = run.stderr.splitlines()
    timing = json.loads(lines[-1])
    capture.verify_clock(timing, tag=tag, cells=shape[0] * shape[1])
    bank = json.loads(lines[0].removeprefix(b"bank ")) if len(lines) > 1 else None
    grid = np.frombuffer(run.stdout, "<f8").reshape(shape)
    if not np.isfinite(grid).all():
        raise ValueError("nonfinite score grid")
    return dict(clock=timing, bank=bank, score_sha256=capture.digest(run.stdout)), grid


def verify_grid(reference, result, selection, channels):
    report = capture.compared(reference, result, selection, channels)
    report["values_compared"] = np.size(reference)
    return report


def package(path, files):
    with (
        path.open("xb") as stream,
        gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for leaf, data in sorted(files.items()):
            member = tarfile.TarInfo(leaf)
            member.size = len(data)
            member.mode = 0o755 if leaf.endswith("-armv7") else 0o644
            archive.addfile(member, io.BytesIO(data))


def run(fixture, work, out, sysroot):
    if os.sched_getaffinity(0) != {5}:
        raise ValueError("use the assigned CPU 5 for the entire comparison")
    work.mkdir(parents=True, exist_ok=False)
    out.mkdir(parents=True, exist_ok=True)
    trust, arrays, src = capture.load_fixture(fixture)
    rate, epoch_count = trust["sample_rate_hz"], trust["epoch_count"]
    selector = capture.archived_selector(src["acquisition.py"])
    channels = arrays["frequencies"]
    shape = (len(channels), epoch_count)
    data = [capture.binary_fixture(arrays, rate, epoch_count)]
    recipes = [None]
    for planted in (True, False):
        raw, recipe = synthetic(arrays, rate, epoch_count, planted)
        data.append(raw)
        recipes.append(recipe)
    inputs = {}
    for case, raw, recipe in zip(SELECTED, data, recipes, strict=True):
        path = work / (case + ".input")
        path.write_bytes(raw)
        inputs[case] = dict(sha256=capture.digest(raw), tag=capture.fixture_tag(raw), recipe=recipe)
    builds = build(work, src[capture.GRID], sysroot)
    libs = [Path("/usr/lib/x86_64-linux-gnu/libfftw3.so.3"), sysroot / "usr/lib/libfftw3.so.3"]
    lock = dict(
        sources={
            p.name: capture.file_sha(p)
            for p in (
                Path(__file__),
                capture.HARNESS,
                src[capture.GRID],
                KERNEL,
                out / "PROTOCOL.md",
            )
        },
        binaries=builds,
        fftw={str(p): capture.file_sha(p) for p in libs},
        input=inputs,
        captured_manifest_sha256=capture.file_sha(fixture),
        captured_iq=trust["iq_sha256"],
        shape=shape,
        host_cpu=5,
        arm_sysroot=str(sysroot),
    )
    save_json(out / "source-lock.json", lock)
    evidence = {}
    for case in SELECTED:
        path = work / (case + ".input")
        tag = inputs[case]["tag"]
        timings = dict(host={"bank": [], "direct": []}, arm={"bank": [], "direct": []})
        grids = {}
        for arch in ("host", "arm"):
            prefix = ["qemu-arm", "-cpu", "cortex-a9", "-L", str(sysroot)] if arch == "arm" else []
            passes = HOST_PASSES if arch == "host" and case == "captured" else 1
            for repeat in range(passes):
                order = ("bank", "direct") if repeat % 2 else ("direct", "bank")
                for method in order:
                    run, grid = attempt(work / method / arch, prefix, path, tag, shape)
                    timings[arch][method].append(run)
                    previous = grids.setdefault(f"{arch}-{method}", grid)
                    if not np.array_equal(previous, grid):
                        raise ValueError("repeated scientific outputs changed")
        reference = grids["host-direct"]
        parity = {
            name: verify_grid(reference, values, selector, channels)
            for name, values in grids.items()
            if name != "host-direct"
        }
        if case == "captured":
            parity["capture-avx2-vs-host-direct"] = verify_grid(
                arrays["scores"], reference, selector, channels
            )
        cpu = {
            arch: {
                name: {
                    stage: median(r["clock"]["stages"][stage]["cpu_ns"] for r in sampled)
                    for stage in ("input_and_validation", "folded_grid_body")
                }
                for name, sampled in pair.items()
            }
            for arch, pair in timings.items()
        }
        evidence[case] = dict(timings=timings, median_stage_cpu_ns=cpu, parity=parity)
        print(case, cpu, flush=True)
        save_json(out / "partial-measurements.json", evidence)
    receipt = dict(source_lock_sha256=capture.file_sha(out / "source-lock.json"), cases=evidence)
    files = {
        "folded-bank-armv7": (work / "bank/arm").read_bytes(),
        "folded-direct-armv7": (work / "direct/arm").read_bytes(),
        "folded.input": (work / "captured.input").read_bytes(),
        "SHA256SUMS": b"",
    }
    files["SHA256SUMS"] = "".join(
        f"{capture.digest(v)}  {k}\n" for k, v in files.items() if k != "SHA256SUMS"
    ).encode()
    package(out / "armv7-benchmark.tar.gz", files)
    receipt["distribution_sha256"] = capture.file_sha(out / "armv7-benchmark.tar.gz")
    save_json(out / "receipt.json", receipt)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, required=True)
    cli.add_argument("--out", type=Path, default=REPORT)
    cli.add_argument("--fixture", type=Path, default=capture.FIXTURE)
    args = cli.parse_args()
    run(args.fixture, local_output(args.work), local_output(args.out), SYSROOT)
