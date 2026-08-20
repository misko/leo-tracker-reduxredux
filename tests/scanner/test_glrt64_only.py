from __future__ import annotations

import numpy as np

from leo.analysis.starlink.pilot_methods import PilotMethod, conditioned_glrt64_score
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame


def test_glrt64_only_score_separates_exact_qin_pilot_from_control() -> None:
    rate = 2_500_000
    epoch = 37
    cfo = 42_000.0
    samples = np.zeros(50_000, dtype=np.complex128)
    template = qin_edge_pilot_frame(rate, "lower")
    frame = 0
    while True:
        start = epoch + round(frame * rate / FRAME_RATE_HZ)
        if start + len(template) > len(samples):
            break
        indexes = np.arange(start, start + len(template))
        samples[start : start + len(template)] += template * np.exp(
            2j * np.pi * cfo * indexes / rate
        )
        frame += 1

    result = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=epoch,
        acquired_cfo_hz=cfo,
        edge="lower",
    )

    assert result.method is PilotMethod.GLRT64
    assert result.margin > 0.5
    assert abs(result.residual_cfo_hz) < 1.0


def test_conditioned_glrt64_uses_selected_edge() -> None:
    rate = 2_500_000
    template = qin_edge_pilot_frame(rate, "upper")
    samples = np.tile(template, 2)[:50_000]

    upper = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=0,
        acquired_cfo_hz=0.0,
        edge="upper",
    )
    lower = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=0,
        acquired_cfo_hz=0.0,
        edge="lower",
    )

    assert upper.margin > lower.margin
