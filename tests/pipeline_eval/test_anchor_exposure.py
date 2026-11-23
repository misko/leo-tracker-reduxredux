from copy import deepcopy

import pytest

from reports.ALGO08.v3 import anchor_exposure as exposure


def source():
    probes = [dict(visit_index=visit, receiver_id=radio, channel=1, edge="lower", actual_rf_hz=10.7e9,
                   candidates=[dict(passed_fractional_margin_gate=radio == 0)])
              for visit in (0, 1, 3, 4, 5, 6, 7, 8, 9) for radio in (0, 1)]
    return dict(source=dict(probes=probes, session_id="id", input_manifest_sha256="manifest",
                            raw_recording_authority_digest="raw"),
                clock_anchor={}, delivery_clocks=[], provenance=dict(window_count=10, processed_windows=9, invalid_capture=1))


def test_schedule_counts_admitted_stereo_visits_and_original_pass_gate():
    original = source()
    rows = list(exposure.enroll(original))
    assert [row[0] for row in rows if row[4] == "anchor"] == [0, 0, 9, 9]
    (anchors, shorts), = exposure.counts(rows)
    assert anchors[:2] == (4, 2)
    assert shorts[:2] == (14, 7)


def test_v3_comparison_uses_identical_signed_opportunities():
    original = source()
    alternative = deepcopy(original)
    alternative["source"]["probes"][0]["candidates"] = []
    (anchors, shorts), = exposure.counts(list(exposure.enroll(alternative, original)))
    assert anchors == (4, 1, 2, 0, 1)
    assert shorts == (14, 7, 7, 0, 0)
    alternative["source"]["probes"][0]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="identical signed opportunities"):
        list(exposure.enroll(alternative, original))


def test_block_bootstrap_keeps_anchor_short_pairs_together():
    by_time = [((2, 0, 0, 0, 0), (14, 0, 0, 0, 0)), ((2, 2, 2, 0, 0), (14, 14, 14, 0, 0))]
    draws = exposure.bootstrap(by_time, True, "test")
    assert set(draws["anchor_rate"]) == {0., .5, 1.}
    assert set(draws["short_minus_anchor"]) == {0.}
    assert set(draws["relative_excess"]) == {0.}
