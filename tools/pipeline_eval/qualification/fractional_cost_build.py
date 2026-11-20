"""Build the grouped integer-epoch refinement over the qualified typed detector."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json
from ..variants.wide_regional import replace
from . import native_hotpath_build as typed
from .fifth_arm import check
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/latency-and-support/fractional-cost"
PARENT = Path.home() / ".cache/leo-native-hotpath-20261119/build-v1"
PARENT_LOCK = typed.REPORT / "result-lock.json"
BASE = "kernel/private/"
PRESENCE = BASE + "native_presence/presence.c"
SEARCH = BASE + "full_search.c"
HEADER = typed.VARIANTS / "fractional_cost_integer.h"
SCOUT = Path(
    "/var/tmp/leo-whole-center-union-20261119/center-union-runtime-v2/libdifferential-scout.so"
)
SCOUT_SHA = "558e5832a1e489c23bff6ec2dd3203a780b9473c7e8284c00290621ee269c4f8"


def presence(source):
    start = source.index("static int glrt(leo_presence_workspace *w, size_t count, int epoch,")
    rotate = source.index("    double complex *rotations=w->glrt_rotations;", start)
    end_rotate = source.index("\n#else\n    double complex *rotations=w->weighted;", rotate)
    loop = source.index("        for (int which = 0; which < 2; ++which) {", start)
    boundary = source.index("\n    }\n    result[2] = 0;", loop)
    done = source.index("\n    return 0;\n}", boundary)
    after = done + len("\n    return 0;\n}")
    frame_block = "\n".join(line[4:] for line in source[loop:boundary].splitlines())
    helper = (
        "#if LEO_PRESENCE_PRECOMPUTE\n"
        "static void glrt_prepare_rotations(leo_presence_workspace *w, double cfo,\n"
        "    double offset, int late)\n{\n" + source[rotate:end_rotate] + "\n}\n#endif\n\n"
        "static void glrt_add_frame(leo_presence_workspace *w, "
        "const double complex correlations[2][64],\n"
        "    double spectra[2][128], double ceilings[2])\n{\n" + frame_block + "\n}\n\n"
        "static void glrt_finish(leo_presence_workspace *w, double spectra[2][128],\n"
        "    const double ceilings[2], double result[3])\n{\n"
        + source[boundary + len("\n    }\n") : done]
        + "\n}\n\n"
    )
    return (
        source[:start]
        + helper
        + source[start:rotate]
        + "    glrt_prepare_rotations(w, cfo, offset, late);"
        + source[end_rotate:loop]
        + "        glrt_add_frame(w, correlations, spectra, ceilings);\n"
        "    }\n    glrt_finish(w, spectra, ceilings, result);\n    return 0;\n}\n\n"
        '#include "fractional_cost_integer.h"' + source[after:]
    )


def search(source):
    return replace(
        source,
        """    candidate->fractional_epoch_status=2;
    for(int k=0;k<5;++k){
        int epoch=(candidate->refined_epoch+k-2+(int)w->n)%(int)w->n;
        double score[3];
        if(glrt(w,count,epoch,candidate->candidate.acquired_cfo_hz,0,
            LEO_PRESENCE_EPOCH_FRAMES,0,score))return -1;""",
        """    candidate->fractional_epoch_status=2;
    double grid[5][3];
    int grouped=leo_grid_four(w,count,candidate->refined_epoch,
        candidate->candidate.acquired_cfo_hz,candidate->candidate.exact_score,
        candidate->candidate.control_score,grid);
    for(int k=0;k<5;++k){
        int epoch=(candidate->refined_epoch+k-2+(int)w->n)%(int)w->n;
        double *score=grid[k];
        if(!grouped && glrt(w,count,epoch,candidate->candidate.acquired_cfo_hz,0,
            LEO_PRESENCE_EPOCH_FRAMES,0,score))return -1;""",
    )


def build(work, reference):
    seal = json.loads(PARENT_LOCK.read_bytes())["files"]
    sealed_source = check(reference / "detector/build-receipt.json", seal["detector-build.json"])
    control = json.loads(sealed_source.read_bytes())
    typed_receipt = json.loads(check(reference / "build.json", seal["build.json"]).read_bytes())
    controls = typed_receipt["libraries"]["hotpath"]
    original = reference / "source"
    for path, digest in control["sources"].items():
        check(original / path, digest)
    source = work / "source"
    shutil.copytree(original, source, ignore=shutil.ignore_patterns("__pycache__"))
    for name, transform in ((PRESENCE, presence), (SEARCH, search)):
        path = source / name
        path.write_text(transform(path.read_text()))
    shutil.copyfile(HEADER, (source / PRESENCE).with_name(HEADER.name))
    gcc = check(Path(control["compiler"]), control["compiler_sha256"])
    ar = check(Path(control["archiver"]), control["archiver_sha256"])
    fftw = typed.ordinary_front_build.HOST_FFTW
    check(fftw / "lib/libfftw3f.a", control["fftw_float_archive_sha256"])
    check(fftw / "include/fftw3.h", control["fftw_header_sha256"])
    temp = work / "tmp"
    temp.mkdir()
    output = work / "detector"
    cmd = [
        sys.executable,
        str(source / "build.py"),
        "--compiler",
        str(gcc),
        "--archiver",
        str(ar),
        "--fftw-prefix",
        str(fftw),
        "--target",
        "host",
        "--output-dir",
        str(output),
        "--work-dir",
        str(work / "objects"),
    ]
    subprocess.run(cmd, env=os.environ | {"TMPDIR": str(temp)}, timeout=60, check=True)
    built = output / "build-receipt.json"
    receipt = json.loads(built.read_bytes())
    diff = {k for k, v in control["sources"].items() if v != receipt["sources"].get(k)}
    copied = str(Path(PRESENCE).with_name(HEADER.name))
    if diff != {PRESENCE, SEARCH} or set(receipt["sources"]) - set(control["sources"]) != {copied}:
        raise ValueError("the detector overlay exceeds the integer grid and shared FFT")
    if receipt["abi_version"] != control["abi_version"]:
        raise ValueError("existing native ABI version changed")
    blob = output / "libleo-adaptive-detector.so"
    trace_base = check(reference / "hotpath" / typed.DETECTOR, controls[typed.DETECTOR])
    if typed.exports(blob) != typed.exports(trace_base):
        raise ValueError("candidate changed the existing native detector exports")
    candidates = {}
    for mode, detector in (("typed", trace_base), ("grouped", blob)):
        folder = work / mode
        folder.mkdir()
        shutil.copyfile(detector, folder / typed.DETECTOR)
        shutil.copyfile(
            check(reference / "hotpath" / typed.LIBRARY, controls[typed.LIBRARY]),
            folder / typed.LIBRARY,
        )
        candidates[mode] = {name: _sha(folder / name) for name in (typed.LIBRARY, typed.DETECTOR)}
    whole = work / "whole"
    whole.mkdir()
    shutil.copyfile(blob, whole / "libleo-adaptive-detector.so")
    shutil.copyfile(check(SCOUT, SCOUT_SHA), whole / SCOUT.name)
    save_json(
        work / "build.json",
        dict(
            closure={str(p): _sha(p) for p in (PARENT_LOCK, Path(__file__), HEADER)},
            control_receipt_sha256=_sha(sealed_source),
            candidate_receipt_sha256=_sha(built),
            pair=candidates,
            whole={p.name: _sha(p) for p in sorted(whole.iterdir())},
            compiler_sha256=_sha(gcc),
            command=cmd,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--reference-build", type=Path, default=PARENT)
    args = parser.parse_args()
    build(args.work, args.reference_build)
