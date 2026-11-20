"""Add one selector to the unchanged persistent dual-lane native join."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants.wide_regional import replace
from . import combined_native_build as combined
from . import dual_lane_build as lane
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-choice/staggered-native"
PARENT = Path("/var/tmp/leo-combined-native-20261119/build")
LIBRARY = "libleo-staggered-native.so"
DETECTOR = lane.hotpath.DETECTOR
SYMBOL = "leo_dual_lane_analyze_staggered_v1"
ORIGINAL = "leo_dual_lane_analyze_v1"


def graft(source):
    source = replace(
        source,
        f"int {ORIGINAL}(dual_lane *ctx, int mode,",
        "static int analyze_pair(dual_lane *ctx, int first, int second,",
    )
    source = replace(
        source,
        "count != times || mode < LEO_HOTPATH_STOCK ||\n        mode > LEO_HOTPATH_ABSENT)",
        "count != times)",
    )
    source = replace(source, "        ctx->mode = mode;", "        ctx->mode = second;")
    source = replace(source, "detect(ctx, 0, iq, mode);", "detect(ctx, 0, iq, first);", count=2)
    return (
        replace(
            source,
            "        detect(ctx, 1, iq, mode);\n    }",
            "        detect(ctx, 1, iq, second);\n    }",
        )
        + f"""

int {ORIGINAL}(dual_lane *ctx, int mode, const int16_t *iq, size_t count,
    leo_native_glrt_result *out, dual_lane_trace *trace)
{{
    if (mode < LEO_HOTPATH_STOCK || mode > LEO_HOTPATH_ABSENT) return LEO_NATIVE_GLRT_INVALID;
    return analyze_pair(ctx, mode, mode, iq, count, out, trace);
}}

int {SYMBOL}(dual_lane *ctx, int fifth_lane, const int16_t *iq, size_t count,
    leo_native_glrt_result *out, dual_lane_trace *trace)
{{
    if (fifth_lane != 0 && fifth_lane != 1) return LEO_NATIVE_GLRT_INVALID;
    const int first = fifth_lane == 0 ? LEO_HOTPATH_FIFTH : LEO_HOTPATH_STOCK;
    const int second = fifth_lane == 1 ? LEO_HOTPATH_FIFTH : LEO_HOTPATH_STOCK;
    return analyze_pair(ctx, first, second, iq, count, out, trace);
}}
"""
    )


def build(work):
    parent_lock = combined.REPORT / "native-lock.json"
    published = whole_iq.read(parent_lock)
    parent_receipt = whole_iq.checked(
        PARENT / "build.json", published["files"]["native-build.json"]
    )
    parent = whole_iq.read(parent_receipt)
    core = whole_iq.checked(PARENT / DETECTOR, parent["files"][DETECTOR])
    original = whole_iq.checked(PARENT / lane.LIBRARY, parent["files"][lane.LIBRARY])
    prior_lock = lane.REPORT / "native-lock.json"
    prior = whole_iq.read(
        whole_iq.checked(
            combined.LANE / "build.json", whole_iq.read(prior_lock)["files"]["native-build.json"]
        )
    )
    source = whole_iq.checked(lane.LANE_C, prior["source_changes"][str(lane.LANE_C)])
    scout = combined.LANE / "dual_lane_scout.c"
    whole_iq.checked(scout, prior["source_changes"][str(scout)])
    archive = lane.hotpath.ordinary_front_build.HOST_FFTW / "lib/libfftw3f.a"
    detector_meta = whole_iq.read(
        whole_iq.checked(PARENT / "detector/build-receipt.json", parent["detector_build_sha256"])
    )
    whole_iq.checked(archive, detector_meta["fftw_float_archive_sha256"])
    gcc = whole_iq.checked(Path(detector_meta["compiler"]), detector_meta["compiler_sha256"])
    header = whole_iq.checked(
        archive.parent.parent / "include/fftw3.h", detector_meta["fftw_header_sha256"]
    )
    work.mkdir(parents=True, exist_ok=False)
    copy = work / source.name
    copy.write_text(graft(source.read_text()))
    shutil.copyfile(scout, work / scout.name)
    shutil.copyfile(core, work / DETECTOR)
    exported = lane.exports(original) | {SYMBOL}
    version = work / "exports.map"
    version.write_text("{ global: " + "; ".join(sorted(exported)) + "; local: *; };\n")
    cmd = [
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
        str(PARENT / "source"),
        "-I",
        str(lane.hotpath.VARIANTS),
        "-I",
        str(work),
        str(copy),
        str(lane.hotpath.VARIANTS / "native_hotpath.c"),
        str(archive),
        str(work / DETECTOR),
        "-lm",
        "-Wl,-rpath,$ORIGIN",
        f"-Wl,--version-script={version}",
        "-o",
        str(work / LIBRARY),
    ]
    subprocess.run(cmd, timeout=30, check=True, env=os.environ | {"TMPDIR": str(work)})
    if lane.exports(work / LIBRARY) != exported or _sha(work / DETECTOR) != _sha(core):
        raise ValueError("staggered detector alters the existing ABI or frozen fractional core")
    files = (
        Path(__file__),
        source,
        scout,
        parent_receipt,
        parent_lock,
        Path(lane.hotpath.VARIANTS / "staggered_native.py"),
    )
    save_json(
        work / "build.json",
        dict(
            files={
                n: _sha(work / n) for n in (LIBRARY, DETECTOR, copy.name, scout.name, version.name)
            },
            sources={str(p): _sha(p) for p in files},
            parent_core_sha256=_sha(core),
            entry=SYMBOL,
            api=sorted(exported),
            command=cmd,
            compiler_sha256=_sha(gcc),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    build(parser.parse_args().work)
