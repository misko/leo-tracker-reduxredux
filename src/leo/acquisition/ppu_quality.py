"""Component-owned AD9361 signed-12-in-CI16 sample quality evidence."""

from __future__ import annotations

from typing import Any

import numpy as np


def signed12_ci16_quality(samples: np.ndarray) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Retain rail contacts and reject words outside the negotiated code range."""
    clipping = [
        int(np.count_nonzero((samples[:, rx] <= -2048) | (samples[:, rx] >= 2047)))
        for rx in range(samples.shape[1])
    ]
    outside = [
        int(np.count_nonzero((samples[:, rx] < -2048) | (samples[:, rx] > 2047)))
        for rx in range(samples.shape[1])
    ]
    flags = ()
    if any(clipping):
        flags += ("adc12_clipping",)
    if any(outside):
        flags += ("adc12_format_unqualified",)
    return flags, {
        "adc12_clipping_components": clipping,
        "adc12_out_of_range_components": outside,
        "sample_code_geometry": "ad9361-signed12-in-ci16-v1",
    }
