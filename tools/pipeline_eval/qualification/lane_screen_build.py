"""Build one new native entry without altering default detector calls."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import lane_screen
from ..variants.wide_regional import replace
from . import native_pruning_build as upstream
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/original-support/lane-screen"
PARENT = Path("/var/tmp/leo-native-pruning-20261119/build")
DETECTOR = "libleo-adaptive-detector.so"
HEADER = Path(lane_screen.__file__).with_suffix(".h")
PRESENCE = "kernel/private/native_presence/presence.c"


def native(source):
    source = replace(
        source,
        '#include "center_union.h"',
        '#include "center_union.h"\n#include "lane_screen.h"',
    )
    source = replace(
        source,
        "const int32_t hints[2],leo_center_union_trace *hint_trace)",
        "const int32_t hints[2],leo_center_union_trace *hint_trace,leo_lane_screen *lane_screen)",
    )
    source = replace(
        source,
        "        context->search->center_union_mask=lane ? selected : NULL;",
        """        context->search->center_union_mask=lane ? selected : NULL;
        context->search->lane_screen=lane_screen ? &lane_screen[rx] : NULL;""",
    )
    source = replace(
        source,
        "        context->search->center_union_mask=NULL;",
        """        context->search->center_union_mask=NULL;
        context->search->lane_screen=NULL;""",
    )
    for old in (
        "result,profile,0,NULL,NULL);",
        "result,profile,1,NULL,NULL);",
        "result,NULL,1,hints,trace);",
    ):
        source = replace(source, old, old[:-2] + ",NULL);", count=2)
    return (
        source
        + f"""

int {lane_screen.ENTRY}(leo_native_glrt *context,const int16_t *samples,
    size_t count,double threshold,leo_native_glrt_result *result,leo_lane_screen trace[2])
{{
    if (!context || context->magic != LEO_NATIVE_GLRT_CONTEXT_MAGIC ||
        context->receiver_count != 2 || context->rate != 10000000 ||
        context->refinement_mode != 3 || !trace ||
        !isfinite(threshold) || threshold < 0 || threshold > 1)
        return LEO_NATIVE_GLRT_INVALID;
    leo_lane_screen measured[2] = {{{{.threshold=threshold}}, {{.threshold=threshold}}}};
    int status=analyze_profiled(context,samples,count,20,20,result,
        NULL,1,NULL,NULL,measured);
    if (!status) memcpy(trace,measured,sizeof(measured));
    return status;
}}
"""
    )


def presence(source):
    return replace(
        source,
        "    const unsigned char *center_union_mask;",
        "    const unsigned char *center_union_mask;\n    leo_lane_screen *lane_screen;",
    )


def full(source):
    return replace(
        source,
        "    if (!nr || retained[0].score<=0) {",
        """    if (w->lane_screen) {
        w->lane_screen->coarse_max=nr ? retained[0].score : 0;
        w->lane_screen->rejected=w->lane_screen->coarse_max < w->lane_screen->threshold;
        if (w->lane_screen->rejected) {
            out.retained_peak_count=(int32_t)nr;
            out.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
            out.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
            *result=out; return 0;
        }
    }
    if (!nr || retained[0].score<=0) {""",
    )


def build(work):
    prior_seal = upstream.REPORT / "result-lock.json"
    lock = whole_iq.read(prior_seal)["files"]
    release = whole_iq.read(whole_iq.checked(PARENT / "build.json", lock["build.json"]))
    parent_path = whole_iq.checked(
        PARENT / "detector/build-receipt.json", release["detector_build_sha256"]
    )
    parent = whole_iq.read(parent_path)
    stock = whole_iq.checked(PARENT / "detector" / DETECTOR, parent["outputs"][DETECTOR])
    for relative, digest in parent["sources"].items():
        whole_iq.checked(PARENT / "source" / relative, digest)
    edits = {"native_glrt.c": native, PRESENCE: presence, upstream.FULL: full}
    copy = work / "source"
    shutil.copytree(PARENT / "source", copy, ignore=shutil.ignore_patterns("__pycache__"))
    for relative, edit in edits.items():
        path = copy / relative
        path.write_text(edit(path.read_text()))
    shutil.copyfile(HEADER, copy / HEADER.name)
    temporary = work / "compiler_tmp"
    temporary.mkdir()
    tools = {
        k: whole_iq.checked(Path(parent[k]), parent[k + "_sha256"])
        for k in ("compiler", "archiver")
    }
    fftw = upstream.combined.lane.hotpath.ordinary_front_build.HOST_FFTW
    whole_iq.checked(fftw / "lib/libfftw3f.a", parent["fftw_float_archive_sha256"])
    whole_iq.checked(fftw / "include/fftw3.h", parent["fftw_header_sha256"])
    command = [
        sys.executable,
        str(copy / "build.py"),
        "--compiler",
        str(tools["compiler"]),
        "--archiver",
        str(tools["archiver"]),
        "--fftw-prefix",
        str(fftw),
        "--target",
        "host",
        "--output-dir",
        str(work / "detector"),
        "--work-dir",
        str(work / "objects"),
    ]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(temporary)}, timeout=65, check=True)
    receipt = work / "detector/build-receipt.json"
    built = whole_iq.read(receipt)
    changed = {name: _sha(copy / name) for name in (*edits, HEADER.name)}
    if built["sources"] != parent["sources"] | changed:
        raise ValueError("source overlay changed an unrelated file")
    candidate = whole_iq.checked(work / "detector" / DETECTOR, built["outputs"][DETECTOR])
    exports = upstream.combined.lane.exports
    if (
        exports(candidate) != exports(stock) | {lane_screen.ENTRY}
        or built["abi_version"] != parent["abi_version"]
    ):
        raise ValueError("existing detector ABI changed")
    save_json(
        work / "build.json",
        dict(
            stock={"path": str(stock), "sha256": _sha(stock)},
            candidate={"path": str(candidate), "sha256": _sha(candidate)},
            stock_build_sha256=_sha(parent_path),
            stock_seal_sha256=_sha(prior_seal),
            candidate_build_sha256=_sha(receipt),
            sources={str(p.relative_to(ROOT)): _sha(p) for p in (HEADER, Path(__file__))},
            changed=changed,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    build(parser.parse_args().work)
