"""Checks for the saved short-primary CFO timestamp audit."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = spec_from_file_location("short_primary_epoch_audit", ROOT / "reports/ALGO08/v3/short_primary_epoch_audit.py")
audit = module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def factor(epoch, *, offset=0., cfo=500., rank=0):
    return dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=offset,
                fractional_tracking_cfo_hz=cfo, candidate_rank=rank)


@pytest.mark.parametrize("pilot_epoch, full_frames, gap_ms", [(400, 15, 4.666667), (13_000, 14, 4.)])
def test_verifier_time_reference_uses_actual_frames(pilot_epoch, full_frames, gap_ms):
    hit = factor(pilot_epoch, offset=.2)
    a, frames = audit.centroid(hit, short=False)
    b, short_frames = audit.centroid(hit, short=True)
    assert short_frames == 8
    assert frames == full_frames
    assert (a-b)*1000 == pytest.approx(gap_ms, abs=1e-5)


def test_same_primary_allows_wrapped_pilot_epoch_but_keeps_signed_cfo():
    original = factor(13_332, offset=.3, cfo=-525.)
    assert audit.good_match(original, factor(0, offset=-.2, cfo=-510.))
    assert not audit.good_match(original, factor(0, offset=-.2, cfo=510.))
    assert not audit.good_match(original, factor(0, offset=-.2, cfo=-510., rank=1))


def test_target_visit_excludes_both_antenna_observations_and_requires_brackets():
    curve = lambda t: 1000. - 2600.*t + 12.*t*t
    donors = [(float(t), t, curve(t)) for t in (-3, -2, -1, 1, 2, 3)]
    donors.extend([(-.5, 9, 1e8), (.5, 9, -1e8)])
    estimate, samples = audit.slope(0., 9, donors)
    assert estimate == pytest.approx(-2600.)
    assert samples == 6
    assert audit.slope(0., 9, [row for row in donors if row[0] != -1. and row[0] != -2.]) is None


def test_fixed_polarity_correction_detects_prespecified_centroid_component():
    points = [dict(change_hz=-.004*s, centroid_hz=-.004*s, slope_hz_s=s,
                   centroid_shift_ms=-4., full_frames=14) for s in (-3000., -1000., 2000.)]
    result = audit.fit_summary(points)
    assert result["corrected"]["rms"] == 0.
    assert result["polarity_reversed"]["rms"] == pytest.approx(2 * result["measured"]["rms"])
    assert result["mse_reduction"] == 1.


def test_chronological_stereo_schedule_and_metadata_provenance():
    from copy import deepcopy

    probes = [dict(visit_index=i, receiver_id=rx, valid_start_counter=100+i*200_000,
                   channel=1, actual_rf_hz=11.5e9, edge="upper", candidates=[])
              for i in range(10) for rx in (0, 1)]
    stock = dict(source=dict(probes=probes, session_id="s", raw_recording_authority_digest="raw",
                             input_manifest_sha256="source"), clock_anchor={"sample_counter": 1})
    short = deepcopy(stock)
    rows = audit.paired_probes(stock, short)
    assert [row[1]["visit_index"] for row in rows if not row[4]] == [0, 0, 8, 8]
    short["source"]["probes"][1]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="valid start counter"):
        audit.paired_probes(stock, short)
