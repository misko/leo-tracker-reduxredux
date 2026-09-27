"""The isolated K1 build must preserve the original engine's science outputs."""

from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from native_candidates import NativeCandidates
from native_engine import NativeTG11


def science(value):
    return {key: item for key, item in asdict(value).items()
            if not key.endswith("_cpu_ms") and not key.endswith("_wall_ms")
            and not key.startswith("_")}


@pytest.mark.parametrize("rate,edge,receiver", (
    (2_500_000, "upper", 0), (5_000_000, "lower", 1),
))
def test_isolated_k1_matches_original_binary(rate, edge, receiver):
    raw = np.random.default_rng(92712 + receiver).integers(
        -16000, 16001, (rate * 120 // 1000, 2, 2), dtype=np.int16,
    )
    raw.setflags(write=False)
    with NativeTG11(rate, edge, library=HERE.parent / "tg11/libtg11.so") as old:
        original_screen = old.screen(raw, receiver=receiver)
        original = old.blind(raw, receiver=receiver, screen=original_screen)
    with NativeCandidates(rate, edge, candidate_budget=1) as new:
        rebuilt_screen = new.screen(raw, receiver=receiver)
        rebuilt = new.blind(raw, receiver=receiver, screen=rebuilt_screen)
    assert science(original_screen) == science(rebuilt_screen)
    assert original  # Exercise actual hypotheses, not only empty-result equality.
    assert [science(row) for row in original] == [science(row) for row in rebuilt]
