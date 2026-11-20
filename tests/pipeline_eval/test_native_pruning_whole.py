import pytest

from tools.pipeline_eval.qualification import native_pruning_whole as trial
from tools.pipeline_eval.qualification import native_pruning_whole_results as results


def test_common_emissions_match_status_and_packet_without_filling_drops():
    packet = {"status": "processed", "full_visit_sha256": "packet"}
    left, right = {0: packet, 1: packet}, {1: packet, 2: packet}
    assert results.matching_emissions(left, right) == {1}
    with pytest.raises(ValueError, match="packets differ"):
        results.matching_emissions(left, {1: packet | {"full_visit_sha256": "different"}})
    with pytest.raises(ValueError, match="packets differ"):
        results.matching_emissions(left, {1: packet | {"status": "invalid_capture"}})


def test_position_support_checks_physical_receiver_pairs_and_keeps_order():
    probes = {
        visit: [dict(receiver_id=lane, visit_index=visit) for lane in (0, 1)] for visit in range(3)
    }
    assert results.emitted_support(probes, {2, 0}) == probes[0] + probes[2]
    with pytest.raises(ValueError, match="both receiver rows"):
        results.emitted_support(probes, {3})
    with pytest.raises(ValueError, match="both receiver rows"):
        results.emitted_support({0: probes[0][::-1]}, {0})


def test_pacing_port_restores_shared_driver_after_the_declared_four_roles():
    old = (trial.pace.CPUS, trial.pace.MODES, trial.pace.MODULE)
    with trial.configuration():
        assert trial.pace.CPUS == {trial.CASE: 0}
        assert trial.pace.MODES == ("pruned", "dense")
    assert old == (trial.pace.CPUS, trial.pace.MODES, trial.pace.MODULE)
