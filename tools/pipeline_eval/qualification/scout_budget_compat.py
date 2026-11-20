"""Verify untouched release entrypoints with genuine synthetic CI16 calls."""

import argparse
import ctypes as ct
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..__main__ import encoded, save_json
from . import ordinary_front_eval, scout_budget_build, scout_budget_eval, wide_regional_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _sha
from .pilot_kernel_eval import _digest


def long_rows(context, samples, stride):
    from leo.analysis.starlink.native_short_window import _ROW_COUNTS, _candidate, _Result

    func = context._library.leo_native_glrt_analyze
    func.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_int16),
        ct.c_size_t,
        ct.c_uint32,
        ct.c_uint32,
        ct.POINTER(_Result),
    ]
    func.restype = ct.c_int
    result = _Result()
    context._check(
        func(
            context._context,
            samples.ctypes.data_as(ct.POINTER(ct.c_int16)),
            len(samples),
            120,
            stride,
            ct.byref(result),
        )
    )
    assert result.row_count == 2 * (1 + 100 // stride)
    return [
        dict(
            {k: getattr(r, k) for k in _ROW_COUNTS},
            candidates=[_candidate(c) for c in r.candidates[: r.candidate_count]],
        )
        for r in result.rows[: result.row_count]
    ]


def compat(work):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    release = scout_budget_eval.release(work)
    results = []
    rate = 10_000_000
    for sample_rate in (2_500_000, 5_000_000, 7_500_000, rate):
        for rx in (1, 2):
            synthetic = wide_regional_eval.synthetic(sample_rate, "lower", rx)
            signal = _test_signal(synthetic, ((735, 116_780, 640),), 82801)
            pair = wide_regional_eval.templates(sample_rate, "lower")
            for fractional in (False, True):
                if sample_rate == rate and fractional:
                    continue
                with ExitStack() as stack:
                    docs = {}
                    for mode in scout_budget_eval.MODES:
                        ctx = stack.enter_context(
                            NativeShortWindow(
                                release["paths"][mode],
                                *pair,
                                sample_rate_hz=sample_rate,
                                receiver_count=rx,
                                fractional_epoch=fractional,
                            )
                        )
                        docs[mode] = ordinary_front_eval._payload(ctx.analyze(signal.samples))
                if encoded(docs["control"]) != encoded(docs["scout16"]):
                    raise ValueError("Unchanged short-window API output changed")
                results.append(
                    dict(
                        geometry=[sample_rate, rx, 20, 20, fractional],
                        payload_sha256=_digest(encoded(docs["control"])),
                    )
                )
    synthetic = wide_regional_eval.synthetic(rate, "upper")
    signal = _test_signal(synthetic, ((735, -116_780, 640),), 82801)
    pair = wide_regional_eval.templates(rate, "upper")
    raw = np.concatenate([signal.samples] * 6)
    with ExitStack() as stack:
        contexts = {
            mode: stack.enter_context(
                NativeShortWindow(
                    release["paths"][mode],
                    *pair,
                    sample_rate_hz=rate,
                    fractional_epoch=True,
                )
            )
            for mode in scout_budget_eval.MODES
        }
        initial = {m: ctx.analyze(signal.samples) for m, ctx in contexts.items()}
        for stride in (10, 20, 120):
            docs = {m: long_rows(ctx, raw, stride) for m, ctx in contexts.items()}
            if encoded(docs["control"]) != encoded(docs["scout16"]):
                raise ValueError("Unchanged long-dwell API output changed")
            results.append(
                dict(
                    geometry=[rate, 2, 120, stride, True],
                    payload_sha256=_digest(encoded(docs["control"])),
                )
            )
        assert {m: ctx.analyze(signal.samples) for m, ctx in contexts.items()} == initial
    return dict(release=release, checked=results, source_sha256=_sha(Path(__file__)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_budget_build.ROOT)
    config = p.parse_args()
    save_json(scout_budget_eval.REPORT / "compatibility.json", compat(config.work))
