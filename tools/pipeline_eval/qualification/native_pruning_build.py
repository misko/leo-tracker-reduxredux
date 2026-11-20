"""Bind exact active-grid publication to the sealed persistent wide detector."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants.wide_regional import replace
from . import combined_native_build as combined
from . import staggered_native_build as staggered
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/pilot-influence/native-pruning"
COMBINED = staggered.PARENT
JOIN = Path("/var/tmp/leo-staggered-native-20261119/build")
HEADER = ROOT / "tools/pipeline_eval/variants/native_pruning.h"
COARSE = "kernel/private/native_presence/coarse_fp32.h"
FULL = "kernel/private/full_search.c"


def coarse(source):
    source = replace(
        source,
        '#include "wide_regional_cfo.h"',
        '#include "wide_regional_cfo.h"\n#include "native_pruning.h"',
    )
    source = replace(
        source,
        "static int coarse_fp32(leo_presence_workspace *w, size_t count)",
        "static int coarse_fp32_execute(leo_presence_workspace *w, size_t count, int sparse)",
    )
    source = replace(
        source,
        "    memset(w->float_accumulated, 0, CFO_COUNT*w->n*sizeof(float));\n"
        "    memset(w->support, 0, w->n*sizeof(int32_t));",
        """    if (sparse) {
        leo_pruning_clear(w->float_accumulated, w->support, CFO_COUNT,
            w->regional_epochs, w->regional_count);
    } else {
        memset(w->float_accumulated, 0, CFO_COUNT*w->n*sizeof(float));
        memset(w->support, 0, w->n*sizeof(int32_t));
    }""",
    )
    old = (
        "    for (int f=0; f<regional_cfo_bins(w); ++f)\n"
        "        for (size_t epoch=0; epoch<w->n; ++epoch)"
    )
    source = replace(
        source,
        old,
        """    if (sparse) {
        leo_pruning_publish(w->grid, w->float_accumulated, w->support, (int)w->n,
            regional_cfo_bins(w), CFO_COUNT, w->regional_epochs, w->regional_count);
        return 0;
    }
"""
        + old,
    )
    return replace(
        source,
        "#pragma GCC pop_options",
        """static int coarse_fp32(leo_presence_workspace *w, size_t count)
{
    return coarse_fp32_execute(w, count, 0);
}

#pragma GCC pop_options""",
    )


def full(source):
    before = "    if (coarse(w,count,NULL)) return -1;\n    out.coarse_cpu_ms="
    return replace(
        source,
        before,
        """#if defined(LEO_PRESENCE_COARSE_FP32) && !LEO_PRESENCE_DIFFERENTIAL_PROPOSAL && \\
    !LEO_PRESENCE_POWER_PROPOSAL && LEO_PRESENCE_COARSE_CI16_FIXED_SCALE
    const int active_only = w->wide_regional && w->rate == 10000000u &&
        w->n == 13333 && count == 200000 && regional_epochs == w->regional_epochs &&
        regional_count == w->regional_count &&
        leo_pruning_valid(regional_epochs, regional_count, (int)w->n);
    if (active_only ? coarse_fp32_execute(w,count,1) : coarse(w,count,NULL)) return -1;
#else
    if (coarse(w,count,NULL)) return -1;
#endif
    out.coarse_cpu_ms=""",
    )


def build(work):
    previous_lock = combined.REPORT / "native-lock.json"
    seal = whole_iq.read(previous_lock)["files"]
    previous = whole_iq.checked(
        COMBINED / "detector/build-receipt.json", seal["detector-build.json"]
    )
    parent = whole_iq.read(previous)
    staged = staggered.REPORT / "result-lock.json"
    lock = whole_iq.checked(JOIN / "build.json", whole_iq.read(staged)["files"]["build.json"])
    join = whole_iq.read(lock)
    before = whole_iq.checked(JOIN / staggered.DETECTOR, join["files"][staggered.DETECTOR])
    if _sha(before) != parent["outputs"][staggered.DETECTOR.removesuffix(".1")]:
        raise ValueError("external join is not bound to the existing combined fractional kernel")
    for name, digest in parent["sources"].items():
        whole_iq.checked(COMBINED / "source" / name, digest)
    source = work / "source"
    shutil.copytree(COMBINED / "source", source, ignore=shutil.ignore_patterns("__pycache__"))
    for name, edit in ((COARSE, coarse), (FULL, full)):
        path = source / name
        path.write_text(edit(path.read_text()))
    leaf = Path(COARSE).with_name(HEADER.name)
    shutil.copyfile(HEADER, source / leaf)
    temp = work / "compiler_tmp"
    temp.mkdir()
    tools = {
        k: whole_iq.checked(Path(parent[k]), parent[k + "_sha256"])
        for k in ("compiler", "archiver")
    }
    fftw = combined.lane.hotpath.ordinary_front_build.HOST_FFTW
    whole_iq.checked(fftw / "lib/libfftw3f.a", parent["fftw_float_archive_sha256"])
    whole_iq.checked(fftw / "include/fftw3.h", parent["fftw_header_sha256"])
    command = [
        sys.executable,
        str(source / "build.py"),
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
    subprocess.run(command, env=os.environ | {"TMPDIR": str(temp)}, check=True, timeout=65)
    receipt = work / "detector/build-receipt.json"
    built = whole_iq.read(receipt)
    changed = {
        name for name, digest in parent["sources"].items() if built["sources"].get(name) != digest
    }
    if changed != {COARSE, FULL} or set(built["sources"]) - set(parent["sources"]) != {str(leaf)}:
        raise ValueError("private coarse overlay changed an unrelated detector source")
    candidate = work / "detector" / staggered.DETECTOR.removesuffix(".1")
    if (
        combined.lane.exports(candidate) != combined.lane.exports(before)
        or built["abi_version"] != parent["abi_version"]
    ):
        raise ValueError("the active-grid detector altered an exported ABI")
    joined = whole_iq.checked(JOIN / staggered.LIBRARY, join["files"][staggered.LIBRARY])
    libraries = {}
    for role, core in (("control", before), ("candidate", candidate)):
        target = work / role
        target.mkdir()
        shutil.copyfile(joined, target / staggered.LIBRARY)
        shutil.copyfile(core, target / staggered.DETECTOR)
        libraries[role] = {path.name: _sha(path) for path in sorted(target.iterdir())}
    save_json(
        work / "build.json",
        dict(
            sources={
                str(p): _sha(p)
                for p in (previous_lock, previous, staged, lock, HEADER, Path(__file__))
            },
            library_sha256=libraries,
            changed={n: built["sources"][n] for n in (*sorted(changed), str(leaf))},
            detector_build_sha256=_sha(receipt),
            argv=command,
            exported_names=sorted(combined.lane.exports(candidate)),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=local_output)
    build(p.parse_args().work)
