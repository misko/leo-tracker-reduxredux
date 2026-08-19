from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink import (
    StarlinkEdge,
    qin_edge_pilot_frame,
    qin_edge_pilot_states,
    template_sha256,
)


def test_qin_appendix_a_states_match_historical_oracle_endpoints() -> None:
    lower = qin_edge_pilot_states(StarlinkEdge.LOWER)

    assert lower.shape == (300, 8)
    assert lower.dtype == np.int8
    assert lower.flags.writeable is False
    assert lower[[0, 1, -2, -1], 0].tolist() == [3, 0, 1, 0]


@pytest.mark.parametrize(
    ("edge", "roll", "sample", "digest"),
    (
        (
            StarlinkEdge.LOWER,
            0,
            complex(0.49843961, 1.17021346),
            "15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657",
        ),
        (
            StarlinkEdge.LOWER,
            17,
            complex(-1.10067379, 0.12092048),
            "5488cbb5e05663193ea83d5b909ebe7a55a78168d0d5cb914c37101720a1fb93",
        ),
        (
            StarlinkEdge.UPPER,
            0,
            complex(0.79843050, -0.08149827),
            "58cfb7745d60f53033bf704598f6d12b8ea25d059b7df185d4d7175088112ff2",
        ),
        (
            StarlinkEdge.UPPER,
            17,
            complex(0.30846128, -0.18039572),
            "48f6e6f23d3e388ad24705a4946ebd4018012326a0a07a1ae6f52e87d5432609",
        ),
    ),
)
def test_legacy_numpy_waveform_has_frozen_complex64_identity(
    edge: StarlinkEdge,
    roll: int,
    sample: complex,
    digest: str,
) -> None:
    # Frozen from leo-tracker edge_pilot_frame, whose NumPy assignment order is
    # intentionally retained. Redux's later scalar materializer has a different
    # byte digest despite agreeing at the documented 1e-7 sample tolerance.
    frame = qin_edge_pilot_frame(2_500_000.0, edge, symbol_roll=roll)

    assert frame.shape == (3333,)
    assert frame.dtype == np.complex64
    assert frame[22] == pytest.approx(sample, abs=1e-7)
    assert template_sha256(frame) == digest
