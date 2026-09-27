from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
TG11 = HERE.parent / "tg11"
sys.path[:0] = [str(HERE), str(TG11)]

from native_engine import NativeTG11  # noqa: E402
from native_guided_boundary import (  # noqa: E402
    NativeGuidedBoundary, SUPPORT_GUARD_HZ, build_library,
)


@pytest.fixture(scope="module")
def library() -> Path:
    return build_library()


def science(value):
    return {
        key: item for key, item in asdict(value).items()
        if not key.endswith("_cpu_ms") and not key.endswith("_wall_ms")
        and not key.startswith("_")
    }


def test_build_receipt_pins_guard_binary_and_sources(library):
    receipt = json.loads(library.with_name(library.name + ".build.json").read_text())
    assert receipt["support_guard_hz"] == SUPPORT_GUARD_HZ
    assert hashlib.sha256(library.read_bytes()).hexdigest() == receipt["binary_sha256"]
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
               for path, digest in receipt["sources_sha256"].items())


def test_blind_and_ordinary_guided_science_match_original(library):
    rate = 2_500_000
    raw = np.random.default_rng(92713).integers(
        -16000, 16001, (rate * 120 // 1000, 2, 2), dtype=np.int16
    )
    before = raw.copy()
    with NativeTG11(rate, "lower", library=TG11 / "libtg11.so") as original:
        old_screen = original.screen(raw, receiver=1)
        old_blind = original.blind(raw, receiver=1, screen=old_screen)
        old_guided = original.guided(
            raw, receiver=1, probe_index=2, predicted_local_epoch_sample=321.25,
            scoring_cfo_hz=50_000.0, expected_physical_cfo_hz=50_000.0,
        )
    with NativeGuidedBoundary(rate, "lower", library=library) as guarded:
        new_screen = guarded.screen(raw, receiver=1)
        new_blind = guarded.blind(raw, receiver=1, screen=new_screen)
        new_guided = guarded.guided(
            raw, receiver=1, probe_index=2, predicted_local_epoch_sample=321.25,
            scoring_cfo_hz=50_000.0, expected_physical_cfo_hz=50_000.0,
        )
        assert guarded.support_guard_hz == SUPPORT_GUARD_HZ
    assert science(old_screen) == science(new_screen)
    assert [science(row) for row in old_blind] == [science(row) for row in new_blind]
    assert old_guided is not None and new_guided is not None
    assert science(old_guided) == science(new_guided)
    assert np.array_equal(raw, before)


def test_roundoff_sized_support_excess_is_scored_without_changing_expected(library):
    rate = 2_500_000
    raw = np.zeros((rate * 120 // 1000, 2, 2), dtype=np.int16)
    scored = 320_268.11034612823
    expected = 206_631.74670976176
    support = 0.5 / 4.4e-6
    assert support < scored - expected < support + SUPPORT_GUARD_HZ
    with NativeTG11(rate, "upper", library=TG11 / "libtg11.so") as original:
        assert original.guided(
            raw, receiver=1, probe_index=0, predicted_local_epoch_sample=3268.0,
            scoring_cfo_hz=scored, expected_physical_cfo_hz=expected,
        ) is None
    with NativeGuidedBoundary(rate, "upper", library=library) as guarded:
        result = guarded.guided(
            raw, receiver=1, probe_index=0, predicted_local_epoch_sample=3268.0,
            scoring_cfo_hz=scored, expected_physical_cfo_hz=expected,
        )
    assert result is not None
    assert result.acquired_cfo_hz == scored


def test_guard_does_not_relax_physical_innovation_and_outside_guard_rejects(library):
    rate = 2_500_000
    raw = np.zeros((rate * 120 // 1000, 2, 2), dtype=np.int16)
    support = 0.5 / 4.4e-6
    scored = 200_000.0
    with NativeGuidedBoundary(rate, "lower", library=library) as guarded:
        wrong = guarded.guided(
            raw, receiver=0, probe_index=0, predicted_local_epoch_sample=10.0,
            scoring_cfo_hz=scored,
            expected_physical_cfo_hz=scored - support - SUPPORT_GUARD_HZ / 2,
        )
        rejected = guarded.guided(
            raw, receiver=0, probe_index=0, predicted_local_epoch_sample=10.0,
            scoring_cfo_hz=scored,
            expected_physical_cfo_hz=scored - support - 2 * SUPPORT_GUARD_HZ,
        )
    assert wrong is not None and wrong.status & 2
    assert not (
        wrong.status == 0 and wrong.supported and wrong.fractional_complete
        and wrong.margin >= 0.025
    )
    assert rejected is None
