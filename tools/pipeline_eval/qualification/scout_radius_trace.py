"""Trace only the prespecified adjacent archive cases without altering released libraries."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import encoded, save_json
from ..variants import iq_stream
from ..variants.wide_regional import replace
from . import (
    ordinary_front_build,
    scout_radius_build,
    scout_radius_eval,
    wide_regional_build,
)
from .full_v5_check import PRODUCERS, _load_case, _sha
from .pilot_kernel_eval import _windows
from .scout_budget_results import unpack
from .wide_regional_eval import templates


def instrument(source):
    source = replace(
        source, '#include "full_search.h"', '#include "full_search.h"\n#include <stdio.h>'
    )
    marker = "    size_t peak_count=collect_active_peaks(w,regional_epochs,regional_count,peaks);"
    source = replace(
        source,
        marker,
        marker
        + """
    fprintf(stderr,"SCOUT_RADIUS_ROW\\n");
    for (int j=0;j<regional_count;++j) {
        int e=regional_epochs[j];
        for (int f=0;f<regional_cfo_bins(w);++f)
            fprintf(stderr,"SCOUT_RADIUS_CELL %d %.0f %a\\n",e,w->frequencies[f],w->grid[f*w->n+e]);
    }
    for (size_t j=0;j<peak_count;++j) {
        int e=peaks[j].epoch, f=peaks[j].coarse_bin;
        fprintf(stderr,"SCOUT_RADIUS_PEAK %d %.0f %a %d\\n",e,w->frequencies[f],peaks[j].score,
            coarse_score_allowed((uint32_t)w->rate,peaks[j].score));
    }
""",
    )
    marker = "    free(peaks);"
    return replace(
        source,
        marker,
        """    for (size_t j=0;j<nr;++j) {
        int e=retained[j].epoch,f=retained[j].coarse_bin;
        fprintf(stderr,"SCOUT_RADIUS_KEEP %d %.0f %a %d\\n",e,w->frequencies[f],retained[j].score,
            coarse_score_allowed((uint32_t)w->rate,retained[j].score));
    }
"""
        + marker,
    )


def build(work, mode):
    base = work / "trace"
    base.mkdir(exist_ok=True)
    target = base / mode
    source = base / f"{mode}-source"
    receipt = json.loads((work / mode / "build-receipt.json").read_bytes())
    original = (
        wide_regional_build.ROOT / "wide-source" if mode == "control" else work / f"{mode}-source"
    )
    if any(_sha(original / f) != d for f, d in receipt["sources"].items()):
        raise ValueError("Trace did not start with the exact released source")
    expected = instrument((original / "kernel/private/full_search.c").read_text())
    if (target / "build-receipt.json").is_file():
        built = json.loads((target / "build-receipt.json").read_bytes())
        library = target / scout_radius_build.LIBRARY
        if (source / "kernel/private/full_search.c").read_text() != expected or _sha(
            library
        ) != built["outputs"][library.name]:
            raise ValueError("Existing trace binary differs from the instrumented release")
        return library
    shutil.copytree(original, source, ignore=shutil.ignore_patterns("__pycache__"))
    full = source / "kernel/private/full_search.c"
    full.write_text(expected)
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(ordinary_front_build.HOST_FFTW),
            "--target",
            "host",
            "--output-dir",
            str(target),
            "--work-dir",
            str(base / f"{mode}-build"),
        ],
        env={**os.environ, "TMPDIR": str(work / "compiler-temp")},
        check=True,
    )
    return target / scout_radius_build.LIBRARY


def trace_rows(data):
    groups = []
    for line in data.splitlines():
        label, *args = line.split()
        if label == "SCOUT_RADIUS_ROW":
            groups.append(dict(cells=[], peaks=[], kept=[]))
        elif label in {"SCOUT_RADIUS_CELL", "SCOUT_RADIUS_PEAK", "SCOUT_RADIUS_KEEP"}:
            kind = {
                "SCOUT_RADIUS_CELL": "cells",
                "SCOUT_RADIUS_PEAK": "peaks",
                "SCOUT_RADIUS_KEEP": "kept",
            }[label]
            groups[-1][kind].append([int(args[0]), int(args[1]), *args[2:]])
        else:
            raise ValueError(f"Unexpected native trace line {line!r}")
    if len(groups) != 2:
        raise ValueError("Trace did not emit exactly two receiver passes")
    return groups


def trace(work):
    runners = {m: build(work, m) for m in scout_radius_eval.MODES}
    folder = work / "trace" / "inputs"
    folder.mkdir(exist_ok=True)
    results = {}
    for case in PRODUCERS:
        table = unpack(scout_radius_eval.REPORT / f"{case}-held.json.gz")
        row = next(r for r in table["rows"] if r["visit"] == 2570)
        with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
            (window,) = _windows(_load_case(case), 5, (10,))
        if row["iq_sha256"] != window.iq_sha256:
            raise ValueError("Target raw trace input differs from held IQ")
        exact, control, iq = (folder / name for name in ("exact.c128", "control.c128", "raw.ci16"))
        for a, b in zip(
            templates(10_000_000, window.target["edge"]), (exact, control), strict=True
        ):
            a.tofile(b)
        window.samples.tofile(iq)
        results[case] = {}
        for mode, path in runners.items():
            argv = [
                sys.executable,
                "-m",
                __spec__.name,
                "--diagnostic-call",
                str(path),
                str(exact),
                str(control),
                str(iq),
            ]
            run = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=15)
            actual = json.loads(run.stdout)["rows"]
            desired = row["payloads"][mode]["rows"]
            if encoded(actual) != encoded(desired):
                raise ValueError("Instrumented diagnostic changed held candidate payload")
            results[case][mode] = dict(
                trace=trace_rows(run.stderr),
                iq_sha256=window.iq_sha256,
                original_payload_sha256=row["payload_sha256"][mode],
            )
    save_json(
        scout_radius_eval.REPORT / "coarse-traces.json",
        dict(
            trace_source_sha256=_sha(Path(__file__)),
            trace_binaries={m: _sha(p) for m, p in runners.items()},
            results=results,
        ),
    )


def diagnostic_call(library, exact, control, raw):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    pair = [np.fromfile(p, dtype="<c16") for p in (exact, control)]
    iq = np.fromfile(raw, dtype="<i2").reshape(200_000, 2, 2)
    with NativeShortWindow(library, *pair, sample_rate_hz=10_000_000, fractional_epoch=True) as ctx:
        sys.stdout.buffer.write(encoded(ctx.analyze(iq)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", default=scout_radius_build.ROOT, type=Path)
    cli.add_argument("--diagnostic-call", nargs=4)
    options = cli.parse_args()
    if options.diagnostic_call:
        diagnostic_call(*options.diagnostic_call)
    else:
        trace(options.work)
