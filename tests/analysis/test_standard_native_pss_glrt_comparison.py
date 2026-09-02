from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import numpy as np

from leo.analysis.standard.native_glrt_epoch import (
    build_standard_native_glrt_epoch_tracking_v1,
)
from leo.analysis.standard.native_pss_glrt_comparison import (
    render_native25_pss_vs_2p5_glrt_png,
)
from leo.contracts.standard_native_glrt_epoch import StandardNativeGlrtEpochTrackingV1
from leo.contracts.standard_native_pss import NativePssSearchOriginV1
from tests.analysis.test_standard_native_glrt_epoch import _DIGEST, _glrt, _source


def _native25_pss() -> Any:
    source = _source(25_000_000)
    times = np.arange(0.5, 5.51, 0.0625)
    origin = float(np.mean(times))
    curvature = 2.4e-7
    drift = 8.0e-6
    mode_ids = tuple(f"sha256:{index:064x}" for index in range(len(times)))
    modes = tuple(
        SimpleNamespace(mode_id=mode_id, center_time_s=float(time_s))
        for mode_id, time_s in zip(mode_ids, times, strict=True)
    )
    track = SimpleNamespace(
        track_id="sha256:" + "f" * 64,
        origin=NativePssSearchOriginV1.INDEPENDENT_BLIND,
        mode_ids=mode_ids,
        time_origin_s=origin,
        coefficients_descending_s=(0.5 * curvature, drift, 0.00031),
        time_start_s=float(times[0]),
        time_stop_s=float(times[-1]),
        rms_residual_us=0.0,
        residuals_us=tuple(0.0 for _ in times),
    )
    return SimpleNamespace(source=source, modes=modes, tracks=(track,))


def test_native25_pss_glrt_comparison_png_is_deterministic() -> None:
    epoch = build_standard_native_glrt_epoch_tracking_v1(
        _glrt(),  # type: ignore[arg-type]
        source_glrt_product_digest=_DIGEST,
    )

    payload = render_native25_pss_vs_2p5_glrt_png(
        (cast(Any, _native25_pss()),),
        (epoch,),
    )

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload == render_native25_pss_vs_2p5_glrt_png(
        (cast(Any, _native25_pss()),),
        (epoch,),
    )


def test_native25_pss_glrt_comparison_publishes_an_empty_diagnostic() -> None:
    epoch = build_standard_native_glrt_epoch_tracking_v1(
        _glrt(),  # type: ignore[arg-type]
        source_glrt_product_digest=_DIGEST,
    )
    empty_pss = SimpleNamespace(source=_source(25_000_000), modes=(), tracks=())

    payload = render_native25_pss_vs_2p5_glrt_png(
        (cast(Any, empty_pss),),
        (cast(StandardNativeGlrtEpochTrackingV1, epoch),),
    )

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
