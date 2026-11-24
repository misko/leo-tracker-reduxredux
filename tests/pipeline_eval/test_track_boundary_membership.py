from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from track_boundary_membership import SAMPLE_RATE, Sample, calibration, membership, piece, segments


def peak(cfo=0., epoch=10):
    return dict(fractional_tracking_cfo_hz=cfo, integer_epoch_sample=epoch, fractional_epoch_offset_samples=0.)


def sample(t, short, stock, mixed):
    return Sample(t*SAMPLE_RATE, short, peak(), stock, mixed)


def test_start_end_contrast_subtracts_same_aperture_control():
    rows = []
    for t in range(17):
        full = t in (1, 3, 5, 8, 11, 13, 15)
        target = peak(100.)
        stock, mixed = target, target
        if not full and t <= 4:
            mixed = None
        if not full and t >= 12:
            stock = None
        rows.append(sample(t, not full, stock, mixed))
    state, data = piece(rows)
    assert state == "both_apertures"
    assert data["short"]["pairs"] == 3
    assert data["full"]["pairs"] == 2
    assert data["short"]["contrast"] - data["full"]["contrast"] == 2.


def test_alignment_ignores_edge_outcomes_and_declines_bad_interior_control():
    p = peak(600., 20)
    rows = [sample(1, False, peak(5000.), peak(5000.)), sample(5, False, p, p), sample(8, False, p, p)]
    assert calibration(rows, 0, 12*SAMPLE_RATE, 3*SAMPLE_RATE) == (600., 10.)
    rows[-1] = sample(8, False, peak(1200., 21), peak(1200., 21))
    assert calibration(rows, 0, 12*SAMPLE_RATE, 3*SAMPLE_RATE) is None


def test_short_and_full_membership_have_same_signed_gate_without_alias_wrap():
    a = sample(1, True, peak(100., 12), peak(100. + 1/4.4e-6, 12))
    assert membership(a, (100., 2.)) == "installed_only"


def test_hardware_gaps_split_and_unsorted_input_fails():
    p = peak()
    rows = [sample(t, True, p, p) for t in (1, 9, 18, 19)]
    assert [[x.counter//SAMPLE_RATE for x in part] for part in segments(rows)] == [[1, 9], [18, 19]]
    with pytest.raises(ValueError, match="not ordered"):
        list(segments(reversed(rows)))
