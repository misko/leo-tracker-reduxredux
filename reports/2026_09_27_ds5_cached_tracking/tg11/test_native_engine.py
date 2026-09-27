from __future__ import annotations

import ctypes as ct
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(NATIVE), str(DEPLOY), str(DEPLOY / "src")]

from known_state_v3 import NativeKnownStateV3  # noqa: E402
from native_engine import NativeTG11, build_library  # noqa: E402
from tools.native_presence import NativePresence, Result, pointer  # noqa: E402


def random_raw(rate: int, seed: int = 7) -> np.ndarray:
    return np.random.default_rng(seed).integers(
        -32768, 32768, (rate * 120 // 1000, 2, 2), dtype=np.int16
    )


def scientific_candidate(candidate) -> tuple:
    return tuple(
        getattr(candidate, name)
        for name, _ in candidate._fields_
        if name not in ("exact_grid", "control_grid")
    ) + (tuple(candidate.exact_grid), tuple(candidate.control_grid))


@pytest.fixture(scope="module")
def library() -> Path:
    return build_library()


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("receiver", [0, 1])
def test_screen_has_eleven_common_dwell_coordinates_and_is_deterministic(library, rate, receiver):
    raw = random_raw(rate, rate + receiver)
    before = raw.copy()
    with NativeTG11(rate, "lower", library) as engine:
        first = engine.screen(raw, receiver=receiver)
        second = engine.screen(raw, receiver=receiver)
    assert len(first.windows) == 11
    assert tuple(window.probe_index for window in first.windows) == tuple(range(11))
    assert tuple(window.probe_start_sample for window in first.windows) == tuple(
        index * rate // 100 for index in range(11)
    )
    assert tuple((window.projected_epoch_sample, window.score) for window in first.windows) == tuple(
        (window.projected_epoch_sample, window.score) for window in second.windows
    )
    assert np.array_equal(raw, before)


@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("probe", [0, 1, 9, 10])
def test_blind_probe_matches_direct_fp32_confirmation(library, receiver, probe):
    rate = 2_500_000
    raw = random_raw(rate, 100 + receiver)
    before = raw.copy()
    start = probe * rate // 100
    packed = np.ascontiguousarray(raw[start:start + rate // 50, receiver, :])
    with NativeTG11(rate, "upper", library) as engine, NativePresence(
        library, rate, "upper"
    ) as direct:
        screen = engine.screen(raw, receiver=receiver)
        all_observations = engine.blind(raw, receiver=receiver, screen=screen)
        observed = tuple(row for row in all_observations if row.probe_index == probe)
        expected = Result()
        assert direct.library.leo_presence_run_ci16(
            direct.workspace, pointer(packed), len(packed), ct.byref(expected)
        ) == 0
    assert len(observed) == expected.candidate_count
    for actual, candidate in zip(observed, expected.candidates):
        assert actual.candidate_index in (0, 1)
        assert actual.fitted
        assert actual.local_epoch_sample == pytest.approx(
            (candidate.epoch + candidate.fractional_offset_samples) % (rate / 750.0), abs=0
        )
        assert actual.acquired_cfo_hz == candidate.acquired_cfo_hz
        assert actual.tracking_cfo_hz == candidate.tracking_cfo_hz
        assert actual.exact_score == candidate.exact_score
        assert actual.control_score == candidate.control_score
        assert actual.margin == candidate.margin
        assert actual.fractional_complete == bool(candidate.fractional_complete)
        assert actual.support_frames in (14, 15)
        assert actual.supported
    assert np.array_equal(raw, before)


def test_five_msps_blind_support_and_candidate_inventory(library):
    rate = 5_000_000
    raw = random_raw(rate, 500)
    with NativeTG11(rate, "lower", library) as engine:
        screen = engine.screen(raw, receiver=1)
        observations = engine.blind(raw, receiver=1, screen=screen)
    assert len(observations) <= 22
    assert {row.probe_index for row in observations}.issubset(set(range(11)))
    assert all(row.supported == (row.valid_bounds and row.support_frames >= 2)
               for row in observations)


def test_blind_requires_existing_same_raw_screen(library):
    rate = 2_500_000
    first = random_raw(rate, 1)
    second = first.copy()
    with NativeTG11(rate, "lower", library) as engine:
        screen = engine.screen(first, receiver=0)
        with pytest.raises(ValueError, match="existing screen"):
            engine.blind(second, receiver=0, screen=screen)
        with pytest.raises(ValueError, match="existing screen"):
            engine.blind(first, receiver=1, screen=screen)


def test_guided_matches_v3_dual_cfo_and_uses_local_then_dwell_coordinates(library):
    rate = 2_500_000
    raw = random_raw(rate, 44)
    probe = 3
    start = probe * rate // 100
    view = raw[start:start + rate // 50, 1, :]
    with NativeTG11(rate, "lower", library) as engine, NativeKnownStateV3(
        rate, "lower", library
    ) as oracle:
        actual = engine.guided(
            raw, receiver=1, probe_index=probe, predicted_local_epoch_sample=1200.25,
            scoring_cfo_hz=103_754.0, expected_physical_cfo_hz=5_210.0,
        )
        expected = oracle.measure(
            view, 1200.25, 103_754.0, expected_physical_cfo_hz=5_210.0,
            recover_timing=False, frame_limit=16,
        )
    assert actual is not None and not actual.fitted
    assert actual.local_epoch_sample == expected["epoch_samples"]
    assert actual.dwell_epoch_sample == start + actual.local_epoch_sample
    assert actual.acquired_cfo_hz == expected["scored_cfo_hz"]
    assert actual.tracking_cfo_hz == expected["tracking_cfo_hz"]
    assert actual.exact_score == expected["exact_score"]
    assert actual.control_score == expected["control_score"]
    assert actual.support_frames == expected["support_frames"]
    assert actual.supported == (expected["valid_bounds"] and expected["support_frames"] >= 2)


def test_zero_is_not_invented_as_supported_observation(library):
    rate = 2_500_000
    raw = np.zeros((rate * 120 // 1000, 2, 2), dtype=np.int16)
    with NativeTG11(rate, "lower", library) as engine:
        screen = engine.screen(raw, receiver=0)
        observations = engine.blind(raw, receiver=0, screen=screen)
    assert all(window.score == 0 for window in screen.windows)
    assert observations == ()


def test_build_receipt_pins_binary_and_sources(library):
    receipt = json.loads(library.with_name(library.name + ".build.json").read_text())
    assert hashlib.sha256(library.read_bytes()).hexdigest() == receipt["binary_sha256"]
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
               for path, digest in receipt["sources_sha256"].items())
