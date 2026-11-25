import pytest

from reports.ALGO08.v3.installed_science_first64 import price, splice_frontier


def original(case, *, complete, hint):
    phases = dict(through_native_write=70., native_to_inventory_write=1., inventory_to_terminal_write=20.,
                  inventory_to_failed_exit=0., terminal_to_exit=8., verifier=1., prefix_cpu_bound={"lower": 55.})
    if not complete:
        phases.update(inventory_to_terminal_write=0., inventory_to_failed_exit=29., terminal_to_exit=0., verifier=0.)
    return dict(case=case, outcome="complete" if complete else "solver_failed", wall=100., phases=phases,
                lookahead=dict(cpu_ns=1_000_000_000, submitted_bytes=10) if hint else None)


def test_free_after_native_and_waits_do_not_erase_paid_prefix_cpu():
    data = price([original("success", complete=True, hint=True), original("failure", complete=False, hint=False)])
    assert data["half"] == 100.
    assert data["joint_gates"]["free_everything_after_native"]["total"] == 140.
    assert data["joint_gates"]["free_waits_and_everything_after_native"]["sum_gap_s"] == 10.
    assert data["joint_gates"]["additionally_free_all_hint_cpu_and_missing_hint_rows"]["total"] == 54.


def test_compose_once_with_disjoint_terminal_tail_preserving_failed_slots():
    data = splice_frontier([original("success", complete=True, hint=True), original("failure", complete=False, hint=False)], .25)
    assert data["free_tail_ceiling"]["total"] == 186.
    assert [r["solver_model"] for r in data["per_case"]] == [5., 0.]
    assert [r["required_prefix_wall_s"] for r in data["per_case"]] == [36., 50.]
    assert data["required_uniform_prefix_fraction"]["both"] == pytest.approx(86./140.)
    with pytest.raises(ValueError, match="fraction"):
        splice_frontier([], 2.)
