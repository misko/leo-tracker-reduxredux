"""Source-geometry and input provenance checks for the distributed aperture."""

import numpy as np
import pytest

from reports.ALGO08.v3.distributed_aperture import (
    FIR_PAD, FRAMES, SAMPLES, STRIDE, WIDTH, origin, possible_input_dependencies, ranges_for_fir,
)
from reports.ALGO08.v3.distributed_aperture_trial import compare_weak


def test_frame_selection_preserves_native_parity_center_and_span():
    assert len(FRAMES) == len(set(FRAMES)) == 8
    assert tuple(13 - index for index in reversed(FRAMES)) == FRAMES
    assert [index % 2 for index in FRAMES] == [0, 1] * 4
    assert [origin(f) for f in FRAMES] == [0, 13333, 53333, 66667, 106667, 120000, 160000, 173333]


def test_each_scored_fir_output_stays_on_its_original_native_tile_and_halo():
    ranges = ranges_for_fir()
    dependencies = possible_input_dependencies()
    active = np.zeros(SAMPLES // STRIDE, bool)
    for (a, b), (first, stop) in zip(ranges, dependencies, strict=True):
        assert a % 4 == b % 4 == 2
        assert first <= a * STRIDE - FIR_PAD
        assert stop >= (b - 1) * STRIDE + FIR_PAD + 1
        active[a:b] = True
    for i in FRAMES:
        start = origin(i, STRIDE) + 88 // STRIDE
        assert active[start:start + WIDTH].all()
    assert active.sum() == 32_304


def test_latest_confirmation_reaches_original_window_end_and_keeps_native_epoch():
    stop = origin(FRAMES[-1]) + 13_332 + 88 + (232 + 64) * 44
    assert stop == 199_777
    assert possible_input_dependencies()[-1][1] >= stop
    assert stop > 120_000


@pytest.mark.parametrize("old, new, matched", [(-190_000., -189_750., 1), (-190_000., 190_000., 0)])
def test_signed_cfo_comparison_does_not_fold_opposite_carriers(old, new, matched):
    def primary(cfo):
        return dict(candidates=[dict(candidate_rank=0, integer_epoch_sample=3000,
                                     fractional_epoch_offset_samples=.2, fractional_tracking_cfo_hz=cfo,
                                     passed_fractional_margin_gate=True)])

    assert compare_weak([primary(old)], [primary(new)])["matched"] == matched
