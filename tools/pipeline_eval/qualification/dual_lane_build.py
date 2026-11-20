"""Build a narrow single-lane union port on the frozen wide detector source closure."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import incremental_rescue_graft as incremental
from ..variants.wide_regional import replace
from . import native_hotpath_build as hotpath
from .full_v5_check import _sha
from .glrt_reuse_build import exports

REPORT = hotpath.REPORT.parents[1] / "latency-and-support/dual-lane"
PIN = "8850a5118fa09c66ec81c8ca14502fceeb73d1c8f39eeff421f184dbf17fc77a"
HOT_WORK = Path.home() / ".cache/leo-native-hotpath-20261119/build-v1"
NEW_SYMBOL = "leo_single_rx_glrt_center_union_short_v1"
LIBRARY = "libleo-dual-lane.so"
LANE_C = hotpath.VARIANTS / "dual_lane_native.c"
API = {f"leo_dual_lane_{letter}_v1" for letter in ("create", "destroy", "analyze", "trace_size")}


def single(source):
    source = replace(
        source,
        "context->receiver_count != 2 || context->refinement_mode != 3 ||",
        "context->refinement_mode != 3 ||",
    )
    return replace(
        source,
        "int leo_single_rx_glrt_analyze_short_window(leo_single_rx_glrt *context,",
        f"""int {NEW_SYMBOL}(leo_single_rx_glrt *context,
    const int16_t *ci16, size_t complex_times, int32_t hint,
    leo_native_glrt_result *result, leo_center_union_trace *trace)
{{
    if(!context||context->magic!=LEO_SINGLE_RX_GLRT_CONTEXT_MAGIC||
       !context->native||context->native->magic!=LEO_NATIVE_GLRT_CONTEXT_MAGIC||
       context->native->receiver_count!=1||!trace)return LEO_NATIVE_GLRT_INVALID;
    const int32_t hints[2]={{hint,-1}};
    return analyze_profiled(context->native,ci16,complex_times,20,20,result,NULL,1,hints,trace);
}}

int leo_single_rx_glrt_analyze_short_window(leo_single_rx_glrt *context,""",
    )


def build(work):
    lock = whole_iq.read(whole_iq.checked(hotpath.REPORT / "result-lock.json", PIN))
    files = lock["files"]
    old = whole_iq.read(whole_iq.checked(hotpath.REPORT / "build.json", files["build.json"]))
    original = whole_iq.read(
        whole_iq.checked(hotpath.REPORT / "detector-build.json", files["detector-build.json"])
    )
    source = HOT_WORK / "source"
    for path, digest in original["sources"].items():
        whole_iq.checked(source / path, digest)
    for path, digest in old["sources"].items():
        whole_iq.checked(Path(path), digest)
    work.mkdir(exist_ok=False, parents=True)
    derived = work / "source"
    shutil.copytree(source, derived, ignore=shutil.ignore_patterns("__pycache__"))
    target = derived / "native_glrt.c"
    target.write_text(single(target.read_text()))
    generated = work / "dual_lane_scout.c"
    generated.write_text(
        incremental.scout((hotpath.VARIANTS / "differential_runtime_fft.c").read_text())
    )
    gcc, ar = Path(original["compiler"]), Path(original["archiver"])
    whole_iq.checked(gcc, original["compiler_sha256"])
    whole_iq.checked(ar, original["archiver_sha256"])
    fftw = hotpath.ordinary_front_build.HOST_FFTW
    library = whole_iq.checked(fftw / "lib/libfftw3f.a", original["fftw_float_archive_sha256"])
    header = whole_iq.checked(fftw / "include/fftw3.h", original["fftw_header_sha256"])
    temporary = work / "tmp"
    temporary.mkdir()
    env = os.environ | {"TMPDIR": str(temporary)}
    args = [
        sys.executable,
        str(derived / "build.py"),
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
    ]
    subprocess.run(args, env=env, timeout=75, check=True)
    receipt = work / "detector/build-receipt.json"
    new = whole_iq.read(receipt)
    expected = original["sources"] | {"native_glrt.c": _sha(target)}
    if new["sources"] != expected:
        raise ValueError("parallel release changed more than the one-lane union port")
    detector = work / "detector" / hotpath.DETECTOR.removesuffix(".1")
    parent_detector = whole_iq.checked(
        HOT_WORK / "hotpath" / hotpath.DETECTOR, old["libraries"]["hotpath"][hotpath.DETECTOR]
    )
    if exports(detector) != exports(parent_detector) | {NEW_SYMBOL}:
        raise ValueError("detector exports changed outside the new one-lane port")
    linked = work / hotpath.DETECTOR
    shutil.copyfile(detector, linked)
    public = work / "dual-lane.exports"
    declared = API | hotpath.API
    public.write_text("{ global: " + "; ".join(sorted(declared)) + "; local: *; };\n")
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
        "-pthread",
        "-I",
        str(header.parent),
        "-I",
        str(derived),
        "-I",
        str(hotpath.VARIANTS),
        "-I",
        str(work),
        str(LANE_C),
        str(hotpath.VARIANTS / "native_hotpath.c"),
        str(library),
        str(linked),
        "-lm",
        "-Wl,-rpath,$ORIGIN",
        f"-Wl,--version-script={public}",
        "-o",
        str(work / LIBRARY),
    ]
    subprocess.run(command, env=env, timeout=30, check=True)
    if exports(work / LIBRARY) != declared:
        raise ValueError("new library has unexpected public symbols")
    programs = (Path(__file__), LANE_C, Path(incremental.__file__), generated, target)
    save_json(
        work / "build.json",
        dict(
            published_hotpath_lock_sha256=PIN,
            input_source_sha256=files["detector-build.json"],
            source_changes={str(p): _sha(p) for p in programs},
            args=args,
            link=command,
            detector_build_sha256=_sha(receipt),
            files={n: _sha(work / n) for n in (LIBRARY, hotpath.DETECTOR)},
            api=sorted(declared),
            source_revision=str(ROOT),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    build(parser.parse_args().work)
