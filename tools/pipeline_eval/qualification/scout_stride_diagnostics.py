"""Audit actual computed CFO cells and binary parity outside the strided path."""

import argparse
import gzip
import json
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import encoded, save_json, write
from ..variants import iq_stream
from . import scout_budget_compat, scout_radius_trace, scout_stride_build, scout_stride_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows
from .scout_budget_results import unpack
from .wide_regional_eval import synthetic, templates

REPORT = scout_stride_eval.REPORT


def check_geometry(work):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    bank = scout_stride_eval.release(work)
    results = []
    for rate, rx, frac, stride in (
        (2_500_000, 2, True, 20),
        (5_000_000, 2, True, 20),
        (7_500_000, 2, True, 20),
        (10_000_000, 1, True, 20),
        (10_000_000, 2, False, 20),
        (10_000_000, 2, True, 10),
        (10_000_000, 2, True, 120),
    ):
        pair = templates(rate, "lower")
        w = _test_signal(synthetic(rate, "lower", rx), ((735, 116_780, 640),), 82801)
        docs = {}
        with ExitStack() as stack:
            for mode, lib in bank["paths"].items():
                context = stack.enter_context(
                    NativeShortWindow(
                        lib,
                        *pair,
                        sample_rate_hz=rate,
                        receiver_count=rx,
                        fractional_epoch=frac,
                    )
                )
                initial = context.analyze(w.samples)
                if stride == 20:
                    docs[mode] = initial
                else:
                    docs[mode] = scout_budget_compat.long_rows(
                        context,
                        np.concatenate([w.samples] * 6),
                        stride,
                    )
                    assert context.analyze(w.samples) == initial
        if encoded(docs["control"]) != encoded(docs["stride"]):
            raise ValueError("Fallback geometry changed its original candidate payload")
        results.append(
            dict(
                rate=rate,
                receivers=rx,
                fractional=frac,
                stride=stride,
                full_payload_sha256=_digest(encoded(docs["control"])),
            )
        )
    return results


def finite_cells(trace):
    return {(e, f): score for e, f, score in trace["cells"] if score != "-inf"}


def diagnostics(work):
    runners = {m: scout_radius_trace.build(work, m) for m in scout_stride_eval.MODES}
    folder = work / "trace" / "stride-inputs"
    folder.mkdir(exist_ok=True)
    results = []
    for case in PRODUCERS:
        study = unpack(REPORT / f"{case}-dev.json.gz")
        with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
            windows = _windows(_load_case(case), 3, (0, 2))
        for w, row in zip(windows, study["rows"], strict=True):
            if row["iq_sha256"] != w.iq_sha256:
                raise ValueError("Diagnostic visit does not match the archived engineering IQ")
            if row["status"] != "processed":
                continue
            files = [folder / name for name in ("exact.c128", "control.c128", "raw.ci16")]
            input_arrays = (*templates(10_000_000, w.target["edge"]), w.samples)
            for p, a in zip(files, input_arrays, strict=True):
                a.tofile(p)
            stacks = {}
            for mode, library in runners.items():
                argv = [
                    sys.executable,
                    "-m",
                    scout_radius_trace.__name__,
                    "--diagnostic-call",
                    str(library),
                    *(str(p) for p in files),
                ]
                run = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=10)
                actual = json.loads(run.stdout)
                if encoded(actual) != encoded(row["payloads"][mode]):
                    raise ValueError("Instrumented library changed the measured candidate payload")
                stacks[mode] = scout_radius_trace.trace_rows(run.stderr)
            rx = []
            for i, (off, on) in enumerate(
                zip(*(stacks[m] for m in scout_stride_eval.MODES), strict=True)
            ):
                original, visited = map(finite_cells, (off, on))
                if not visited.keys() <= original.keys():
                    raise ValueError("Strided coarse search escaped the original region")
                exact = sum(v == original[k] for k, v in visited.items())
                rx.append(
                    dict(
                        receiver=i,
                        full_cells=len(original),
                        stride_cells=len(visited),
                        identical_retained_scores=exact,
                        delta_count=len(visited) - exact,
                        repaired_odd=sum((f + 800_000) % 160_000 != 0 for _, f in visited),
                    )
                )
            results.append(
                dict(
                    id=case, visit=row["visit"], iq_sha256=w.iq_sha256, receivers=rx, traces=stacks
                )
            )
    write(
        REPORT / "grid-traces.json.gz",
        gzip.compress(
            encoded(
                dict(
                    trace_program_sha256=_sha(Path(scout_radius_trace.__file__)),
                    diagnostic_program_sha256=_sha(Path(__file__)),
                    libraries={m: _sha(p) for m, p in runners.items()},
                    rows=results,
                )
            ),
            mtime=0,
        ),
    )
    save_json(REPORT / "compatibility.json", dict(results=check_geometry(work)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_stride_build.ROOT)
    diagnostics(p.parse_args().work)
