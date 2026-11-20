import pytest

from tools.pipeline_eval.qualification import parallel_position as fit
from tools.pipeline_eval.qualification import rf_lane_position as route
from tools.pipeline_eval.qualification import rf_lane_position_results as results


def pair(visit, rf, first_pass, second_pass):
    return tuple(
        dict(
            visit_index=visit,
            receiver_id=i,
            actual_rf_hz=rf,
            candidates=[dict(passed_fractional_margin_gate=passed)],
        )
        for i, passed in enumerate((first_pass, second_pass))
    )


def test_full_and_measured_assignment_keep_each_valid_stereo_pair_indivisible():
    wide = {0: pair(0, 12, True, False), 2: pair(2, 17, False, True)}
    original = {0: pair(0, 12, False, True), 2: pair(2, 17, True, False)}
    donor, choices = route.complete_assignment(wide, original, "1" * 64)
    assert set(v[0] for v in choices.values()) == {"wide", "original"}
    for visit, (role, probes) in choices.items():
        source = original if probes[0]["actual_rf_hz"] == donor else wide
        assert (source is original) == (role == "original")
        assert probes is source[visit]
    with pytest.raises(ValueError, match="valid visit sets"):
        route.complete_assignment(wide, {0: original[0]}, "1" * 64)


def test_audit_rejects_unassigned_reply_even_when_the_payload_is_plausible():
    p = pair(0, 50, True, False)
    opts = {0: ("original", p)}
    row = dict(visit=0, admission="queued", observed_by_cutoff=True)
    route.verify_emissions([row], [(100, 110, p)], opts, "original", 110)
    with pytest.raises(ValueError, match="wrong detector"):
        route.verify_emissions([row], [(100, 110, p)], opts, "wide", 110)
    with pytest.raises(ValueError, match="availability"):
        route.verify_emissions([row], [(100, 111, p)], opts, "original", 110)


def test_scheduled_fit_cannot_disappear_for_an_unassigned_cpu(tmp_path):
    with pytest.raises(ValueError, match="available worker"):
        fit.fit_jobs(tmp_path, tmp_path, [{"cpu": 1}], (2,))


def test_independent_complete_fits_match_both_positions_and_packets_despite_different_times():
    keys = dict(paired_capture_sha256="a", original_request_sha256="b", catalog_sha256="c", tile={})
    arms = {"c0": {"latlon": [11, 12]}, "fitted_c": {"latlon": [11.1, 12.1]}}
    row = dict(
        id="sample",
        selected_visits=8,
        original_visits=1,
        configured_rf_hz=70,
        probe_sha256="sha256:d",
        result=dict(arms=arms, metrics=dict(stage_s=10, tracks=5)),
        **keys,
    )
    other = dict(id="sample", result=dict(arms=arms, metrics=dict(stage_s=22, tracks=5)), **keys)
    audit = dict(
        complete_probes_sha256={"whole": "d"},
        valid_visits=8,
        original_visits=1,
        assigned_rf_hz=70,
        **keys,
    )
    assert results.match_complete(row, other, audit)["visits"] == 8
    with pytest.raises(ValueError, match="disagree"):
        results.match_complete(row, other, dict(audit, complete_probes_sha256={"whole": "e"}))
    other["result"]["arms"] = dict(arms, fitted_c={"latlon": [11.2, 12.1]})
    with pytest.raises(ValueError, match="disagree"):
        results.match_complete(row, other, audit)
