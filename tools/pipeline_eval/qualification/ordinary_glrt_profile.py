"""Measure cold and reused contexts separately on each architecture and build."""

import argparse
import csv
import gzip
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import iq_stream
from . import ordinary_front_build, ordinary_glrt_eval
from .full_v5_check import NATIVE_LIBRARY, PRODUCERS, _load_case, _sha
from .pilot_kernel_eval import _windows

C_SOURCE = Path(__file__).with_suffix(".c")


def run(case, arch, work):
    report = ordinary_glrt_eval.REPORT
    table = json.loads(gzip.decompress((report / f"{case}-{arch}.json.gz").read_bytes()))
    first = next(row for row in table["rows"] if row["status"] == "processed")
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", ordinary_glrt_eval.CHUNK_PREFIX):
        (window,) = _windows(_load_case(case), first["segment"], (first["sequence"],))
    if window.iq_sha256 != first["iq_sha256"]:
        raise ValueError("Cold profile source differs from the first held input")
    host = arch == "host"
    control = NATIVE_LIBRARY.parent if host else ordinary_front_build.ARM_CONTROL
    receipt = json.loads((control / "build-receipt.json").read_bytes())
    sysroot = Path(receipt["fftw_double_library"]).parents[2]
    base = work / f"{case}-{arch}-profile"
    base.mkdir(exist_ok=False)
    runner = base / "steady"
    samples = base / "input.ci16"
    window.samples.tofile(samples)
    subprocess.run(
        [
            receipt["compiler"],
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ordinary_front_build.SOURCE),
            str(C_SOURCE),
            "-L",
            str(control),
            "-lleo-adaptive-detector",
            "-o",
            str(runner),
        ],
        check=True,
    )
    templates = work / f"{case}-arm-input"
    results = {}
    for mode, original in zip(ordinary_glrt_eval.MODES, (control, work / arch), strict=True):
        library = original / NATIVE_LIBRARY.name
        alias = base / "libleo-adaptive-detector.so.1"
        alias.symlink_to(library)
        rss = base / "rss.txt"
        argv = [
            str(runner),
            str(samples),
            str(templates / "exact.c128"),
            str(templates / "control.c128"),
        ]
        env = os.environ.copy()
        if host:
            env["LD_LIBRARY_PATH"] = str(base)
        else:
            argv = [
                "qemu-arm",
                "-cpu",
                "cortex-a9",
                "-L",
                str(sysroot),
                "-E",
                f"LD_LIBRARY_PATH={base}",
                *argv,
            ]
        out = subprocess.run(
            ["/usr/bin/time", "-f", "%M", "-o", str(rss), *argv],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        alias.unlink()
        context, *lines = out.stdout.splitlines()
        results[mode] = dict(
            library_sha256=_sha(library),
            init_wall_ms=float(context),
            peak_rss_kib=int(rss.read_text()),
            calls=[{k: float(v) for k, v in r.items()} for r in csv.DictReader(lines)],
        )
    save_json(
        report / f"{case}-{arch}-profile.json",
        dict(
            case=case,
            visit=first["visit"],
            iq_sha256=window.iq_sha256,
            modes=results,
            runner_sha256=_sha(C_SOURCE),
            driver_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", required=True, type=Path)
    cli.add_argument("--case", choices=PRODUCERS, required=True)
    args = cli.parse_args()
    for arch in ("host", "arm"):
        run(args.case, arch, local_output(args.work))
