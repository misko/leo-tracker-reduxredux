import copy

import pytest

from tools.pipeline_eval.qualification.one_lane_roster import audit_projection
from tools.pipeline_eval.qualification.one_lane_roster_results import comparisons
from tools.pipeline_eval.variants.one_lane_schedule import project


def input_document():
    return dict(
        delivery_clocks=list(range(5)),
        last_sample_counter=100,
        source=dict(
            input_manifest_sha256="stock-clock",
            analysis_manifest_sha256="stock-analysis",
            probes=[
                dict(
                    visit_index=visit,
                    receiver_id=rx,
                    channel=channel,
                    edge="lower",
                    valid_start_counter=20 * visit,
                    candidates=[dict(passed_fractional_margin_gate=rx == 0, margin=rx - visit)],
                )
                for visit, channel in ((0, 1), (2, 2), (3, 1), (4, 2))
                for rx in (0, 1)
            ],
        ),
        provenance=dict(
            window_count=5,
            processed_windows=4,
            invalid_capture=1,
            detector_sha256="source-stock-sha",
            excluded_windows=[dict(visit=1)],
        ),
    )


def test_stock_projection_keeps_every_physical_slot_and_skips_invalid_turn():
    stock = input_document()
    projected, schedule = project(stock, {(1, "lower"): 100, (2, "lower"): 200})
    assert [(row["visit"], row["selected_receiver"]) for row in schedule] == [
        (0, 0),
        (2, 0),
        (3, 1),
        (4, 1),
    ]
    result = audit_projection(stock, projected, schedule)
    assert result == dict(
        valid_visits=4,
        masked_probe_rows=4,
        stock_positive_probes=4,
        positive_probes=2,
        stock_candidates=8,
        retained_candidates=4,
    )
    assert len(stock["source"]["probes"]) == len(projected["source"]["probes"])
    assert all(probe["candidates"] for probe in stock["source"]["probes"])


def test_suppressed_payload_must_be_empty_and_keep_physical_counter():
    stock = input_document()
    projected, schedule = project(stock, {(1, "lower"): 100, (2, "lower"): 200})
    changed = copy.deepcopy(projected)
    changed["source"]["probes"][1]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="suppressed lane"):
        audit_projection(stock, changed, schedule)
    changed = copy.deepcopy(projected)
    changed["source"]["probes"][1]["candidates"] = stock["source"]["probes"][1]["candidates"]
    with pytest.raises(ValueError, match="suppressed lane"):
        audit_projection(stock, changed, schedule)
    del changed["source"]["probes"][1]
    with pytest.raises(ValueError, match="complete physical stereo visits"):
        audit_projection(stock, changed, schedule)


def test_directional_tolerance_distinguishes_a_material_improvement(monkeypatch):
    scores = [
        dict(id="case", method=method, arm="c0", baseline_km=2.0, error_km=error)
        for method, error in (("complete_four_regions", 3.0), ("one_lane_roster", 1.0))
    ]
    monkeypatch.setattr(
        "tools.pipeline_eval.qualification.one_lane_roster_results.fixed.scored",
        lambda *_: scores,
    )
    _, candidate = comparisons(None, None)
    assert candidate["delta_pct_original"] == -50
    assert candidate["at_most_5pct_above_stock"]
    assert not candidate["within_symmetric_10pct_original"]
