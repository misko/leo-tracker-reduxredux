import pytest

from reports.ALGO08.v3.stereo_cfo_shrink import HERTZ, energy, pair_modes, predict


def visit(index, hz0, hz1, *, short=True, delay=0):
    rows = {}
    for radio, hz in enumerate((hz0, hz1)):
        oid = f"{index}-{radio}"
        row = dict(channel=1, actual_rf_hz=20_000, edge="lower", valid_start_counter=index * 1000,
                   visit_index=index, receiver_id=radio)
        factor = {HERTZ: hz, "integer_epoch_sample": 24, "fractional_epoch_offset_samples": radio * delay}
        rows[oid] = dict(id=oid, row=row, counter=row["valid_start_counter"], radio=radio,
                         short=short, factor=factor if hz is not None else None)
    return rows


def test_direct_and_history_preserve_pair_mean_and_ignore_anchor_outputs():
    history = {}
    for i in range(3):
        history.update(visit(i, 500, 800, short=False))
    changes, counts = predict(history | visit(3, 700, 1080))
    assert changes == {"3-0": (20., "3-1"), "3-1": (-20., "3-0")}
    assert counts["history_visits"] == 1
    changes, _ = predict(visit(0, -10., 30.) | visit(1, 3, None) | visit(2, 3, 50, delay=3))
    assert changes == {"0-0": (10., "0-1"), "0-1": (-10., "0-0")}
    assert predict(visit(0, 3, 300))[0] == {}


def test_stereo_modes_leave_common_difference_intact_and_preserve_enrollment():
    candidate = visit(2, 180, 220)
    changes, _ = predict(candidate)
    values = pair_modes(visit(2, 120, 100), candidate, changes)
    assert energy(values["strict"]) == dict(visits=1, common_sq_hz2=8100, diff_before_sq_hz2=900,
                                            diff_after_sq_hz2=400, max_removable_fraction=.1)
    assert not pair_modes(visit(2, None, 1), candidate, changes)
    wider = pair_modes(visit(2, -200, 100), candidate, changes)
    assert "strict" not in wider and len(wider["epoch_close"]) == 1


def test_wrong_channel_or_stale_time_rejected():
    rows = visit(0, 3, 80)
    rows["0-1"]["row"]["channel"] += 1
    with pytest.raises(ValueError, match="same signed visit"):
        predict(rows)
    with pytest.raises(ValueError, match="advancing"):
        predict(visit(2, 3, 4) | visit(1, 4, 5))
