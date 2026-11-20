"""Build a new typed wide receiver from the sealed center-union source."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json
from ..variants.wide_regional import replace
from . import fifth_arm, ordinary_front_build
from .full_v5_check import _sha
from .glrt_reuse_build import exports

REPORT = ROOT / "reports/2026_11_19_receiver_screening/arrival-and-timing/native-hotpath"
VARIANTS = ROOT / "tools/pipeline_eval/variants"
STOCK = Path("/var/tmp/leo-frontier-whole-20261119/wide-stock.so")
UNION = Path("/var/tmp/leo-center-union-20261119/union/libleo-adaptive-detector.so")
DERIVED = "kernel/private/proposal_core.c"
FOLD = "native_hotpath_fold.h"
DETECTOR = "libleo-adaptive-detector.so.1"
LIBRARY = "libleo-native-hotpath.so"
API = {
    f"leo_native_hotpath_{n}_v1"
    for n in ("create", "destroy", "analyze", "trace_size", "result_size")
}


def overlay(source):
    source = replace(
        source,
        "static void fold_three(fftwf_complex *out[3]",
        '#include "native_hotpath_fold.h"\n\nstatic void fold_three(fftwf_complex *out[3]',
    )
    return replace(
        source,
        "#else\n    fold_three_scalar(out,raw,start,off,valid,rx);",
        """#else
#ifdef LEO_NATIVE_HOTPATH_AVX2
    __builtin_cpu_init();
    if (__builtin_cpu_supports("avx2")) {
        size_t k=native_hotpath_fold4(out,raw,start,off,valid,rx);
        for(int m=0;m<3;++m)
            fold_scalar(out[m]+k,raw,start,off+k,valid[m]-k,rx,lags[m]);
        return;
    }
#endif
    fold_three_scalar(out,raw,start,off,valid,rx);""",
    )


def build(work, source):
    sources = fifth_arm.UNION / "build-receipt.json"
    identity = json.loads((fifth_arm.UNION / "release.json").read_bytes())
    control = json.loads(sources.read_bytes())
    fifth_arm.check(STOCK, identity["library_sha256"]["stock"])
    fifth_arm.check(UNION, identity["library_sha256"]["union"])
    for name, digest in control["sources"].items():
        fifth_arm.check(source / name, digest)
    private = work / "source"
    shutil.copytree(source, private, ignore=shutil.ignore_patterns("__pycache__"))
    target = private / DERIVED
    target.write_text(overlay(target.read_text()))
    shutil.copyfile(VARIANTS / FOLD, target.with_name(FOLD))
    gcc = fifth_arm.check(Path(control["compiler"]), control["compiler_sha256"])
    ar = fifth_arm.check(Path(control["archiver"]), control["archiver_sha256"])
    fftw = ordinary_front_build.HOST_FFTW
    archive = fifth_arm.check(fftw / "lib/libfftw3f.a", control["fftw_float_archive_sha256"])
    include = fifth_arm.check(fftw / "include/fftw3.h", control["fftw_header_sha256"]).parent
    temp = work / "tmp"
    temp.mkdir()
    env = os.environ | {"TMPDIR": str(temp)}
    subprocess.run(
        [
            sys.executable,
            str(private / "build.py"),
            "--compiler",
            str(gcc),
            "--archiver",
            str(ar),
            "--fftw-prefix",
            str(fftw),
            "--target",
            "host",
            "--output-dir",
            str(work / "detector"),
            "--work-dir",
            str(work / "objects"),
        ],
        env=env,
        check=True,
        timeout=75,
    )
    modified = json.loads((work / "detector/build-receipt.json").read_bytes())
    got = modified["sources"]
    if (
        set(got) - set(control["sources"]) != {str(Path(DERIVED).with_name(FOLD))}
        or {n for n, sha in control["sources"].items() if got.get(n) != sha} != {DERIVED}
        or modified["abi_version"] != control["abi_version"]
    ):
        raise ValueError("wide detector source differs outside the proposal implementation")
    output = work / "detector/libleo-adaptive-detector.so"
    if exports(output) != exports(UNION):
        raise ValueError("the existing detector ABI differs")
    export_map = work / "hotpath.exports"
    export_map.write_text("{ global: " + "; ".join(sorted(API)) + "; local: *; };\n")
    libraries, commands = {}, {}
    for role, detector in (("reference", UNION), ("hotpath", output)):
        folder = work / role
        folder.mkdir()
        shutil.copyfile(detector, folder / DETECTOR)
        command = [
            str(gcc),
            "-std=c11",
            "-shared",
            "-fPIC",
            "-O3",
            "-ffp-contract=off",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(include),
            "-I",
            str(private),
            "-I",
            str(VARIANTS),
            *(["-DLEO_HOTPATH_REFERENCE"] if role == "reference" else []),
            str(VARIANTS / "native_hotpath.c"),
            str(archive),
            str(folder / DETECTOR),
            "-lm",
            "-Wl,-rpath,$ORIGIN",
            f"-Wl,--version-script={export_map}",
            "-o",
            str(folder / LIBRARY),
        ]
        subprocess.run(command, env=env, check=True, timeout=30)
        if exports(folder / LIBRARY) != API:
            raise ValueError("typed shared library exports more than the declared ABI")
        commands[role] = command
        libraries[role] = {n: _sha(folder / n) for n in (LIBRARY, DETECTOR)}
    save_json(
        work / "build.json",
        dict(
            control_sha256=_sha(sources),
            original_stock_sha256=_sha(STOCK),
            original_union_sha256=_sha(UNION),
            candidate_receipt_sha256=_sha(work / "detector/build-receipt.json"),
            libraries=libraries,
            commands=commands,
            api=sorted(API),
            compiler_sha256=_sha(gcc),
            archive_sha256=_sha(archive),
            sources={
                str(p): _sha(p)
                for p in (
                    Path(__file__),
                    VARIANTS / FOLD,
                    VARIANTS / "native_hotpath.c",
                    VARIANTS / "native_hotpath.h",
                    VARIANTS / "native_hotpath_rank.h",
                    VARIANTS / "differential_runtime_fft.c",
                )
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--source", type=Path, default=fifth_arm.UNION_SOURCE)
    args = parser.parse_args()
    build(args.work, args.source)
