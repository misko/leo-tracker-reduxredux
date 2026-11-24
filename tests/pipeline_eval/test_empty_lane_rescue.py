import pytest

from reports.ALGO08.v3.empty_lane_rescue import counts, schedule


def lanes(*visits):
    rows = {}
    for counter, (channel, short, present) in enumerate(visits):
        for radio in (0, 1):
            oid = f"{counter}/{radio}"
            rows[oid] = dict(id=oid, radio=radio, counter=counter, short=short,
                             row=dict(edge="upper", channel=channel, actual_rf_hz=channel),
                             factor={"positive": True} if present[radio] else None)
    return rows


def test_original_visits_drive_decisions_for_current_empty_lanes_only():
    rows = lanes((1, False, (True, False)), (2, False, (False, False)), (1, True, (False, True)),
                 (2, True, (False, True)), (1, True, (False, False)), (1, True, (False, False)))
    assert schedule(rows) == {"2/0": "both", "3/0": "peer", "4/0": "neither", "4/1": "previous",
                              "5/0": "neither", "5/1": "neither"}
    assert schedule(dict(list(rows.items())[:-2])).items() <= schedule(rows).items()


def test_counts_include_unselected_reference_and_all_charged_retries():
    summary = counts({"a": "neither", "b": "peer", "c": "previous", "d": "both"}, {"a", "b"})
    assert (summary["selected"], summary["reference"], summary["hits"]) == (3, 2, 1)
    assert summary["recall"] == .5 and summary["precision"] == 1/3
    assert counts({}, {})["recall"] is None
    with pytest.raises(ValueError):
        counts({}, {"other"})


def test_receiver_rows_require_stereo_pairing():
    rows = lanes((1, False, (True, False)))
    rows["0/1"]["radio"] = 0
    with pytest.raises(ValueError):
        schedule(rows)
    with pytest.raises(ValueError):
        schedule({"0/0": rows["0/0"]})
