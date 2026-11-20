"""Check canonical radius-one outputs outside the new dual/fractional entrypoint."""

from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..__main__ import encoded, save_json
from . import scout_budget_compat, scout_radius_build, scout_radius_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _sha
from .pilot_kernel_eval import _digest
from .wide_regional_eval import synthetic, templates


def compat(work):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    release = scout_radius_eval.release(work)
    results = []
    for rate, rx, frac, stride in (
        (5_000_000, 2, True, 20),
        (10_000_000, 1, True, 20),
        (10_000_000, 2, False, 20),
        (10_000_000, 2, True, 10),
        (10_000_000, 2, True, 120),
    ):
        input_ = _test_signal(synthetic(rate, "lower", rx), ((735, 116_780, 640),), 82801)
        pair = templates(rate, "lower")
        docs = {}
        with ExitStack() as stack:
            for mode, path in release["paths"].items():
                ctx = stack.enter_context(
                    NativeShortWindow(
                        path,
                        *pair,
                        sample_rate_hz=rate,
                        receiver_count=rx,
                        fractional_epoch=frac,
                    )
                )
                if stride != 20:
                    ctx.analyze(input_.samples)
                    docs[mode] = scout_budget_compat.long_rows(
                        ctx,
                        np.concatenate([input_.samples] * 6),
                        stride,
                    )
                else:
                    docs[mode] = ctx.analyze(input_.samples)
        if encoded(docs["control"]) != encoded(docs["radius2"]):
            raise ValueError("An out-of-scope API changed the candidate slate")
        results.append(
            dict(
                rate=rate,
                receivers=rx,
                fractional=frac,
                stride=stride,
                payload_sha256=_digest(encoded(docs["control"])),
            )
        )
    save_json(
        scout_radius_eval.REPORT / "compatibility.json",
        dict(
            release=release,
            results=results,
            source_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    compat(scout_radius_build.ROOT)
