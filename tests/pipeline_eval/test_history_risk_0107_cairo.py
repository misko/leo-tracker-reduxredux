from copy import deepcopy

import pytest

from reports.ALGO08.v3.history_risk_0107_cairo import same_withhold, scan_opportunities, summarize


def test_withhold_comparison_rejects_changed_factor_or_any_publication():
    ordinary = dict(science=dict(arms={"c0": {"latlon": None}, "fitted_c": {"latlon": None}}), digest="same",
                    opportunities="same", excluded=[0, 12], factors=19, figures={}, sidecars=None, route=None)
    same_withhold(deepcopy(ordinary), ordinary)
    for corrupt in (dict(figures={"position": "false"}), dict(opportunities="changed"), dict(factors=18),
                    dict(sidecars={"path": "false"}), dict(route="rendered")):
        with pytest.raises(ValueError, match="zero-product"):
            same_withhold(ordinary | corrupt, ordinary)


def test_median_is_the_median_of_ratios_and_must_pass_alongside_the_sum():
    def row(candidate, stock):
        return {arm: dict(elapsed_s=value, cpu_s=value, exit_code=0)
                for arm, value in (("candidate", candidate), ("stock", stock))}

    clocks = {"DS30-0107": row(.4, 1.), "DS30-0016": row(7.5, 10.)}
    result = summarize(clocks)
    assert result["timing"]["elapsed_s"]["median_ratio"] == pytest.approx(.575)
    assert result["timing"]["elapsed_s"]["summed_ratio"] == pytest.approx(7.9/11)
    assert result["gates"]["1.6x"] == dict(median=True, sum=False, both=False)
    clocks["DS30-0107"]["candidate"]["exit_code"] = 1
    with pytest.raises(ValueError, match="successful exits"):
        summarize(clocks)


def test_scan_identity_keeps_opportunities_when_factor_counts_differ():
    scan = dict(window_count=2, counts={"processed": 1}, recording_name="a", session_id="b", time_basis="hardware",
                rf_mapping_authorities=["measured"], channels=[dict(channel=1, receiver_id=0, processed=1, skipped=0, strong=1)],
                points=[dict(channel=1, receiver_id=0, cfo_hz=123)])
    deployed = deepcopy(scan)
    deployed["channels"][0]["strong"] = 0
    deployed["points"] = []
    assert scan_opportunities(deployed) == scan_opportunities(scan)
    deployed["channels"][0]["skipped"] = 1
    assert scan_opportunities(deployed) != scan_opportunities(scan)
