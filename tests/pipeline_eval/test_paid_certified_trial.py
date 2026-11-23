from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import paid_certified_trial

    return paid_certified_trial


def test_input_pair_requires_original_packet_and_paid_mask(trial):
    expected = {key: key for key in (*trial.PAIRED_FIELDS, "native_sha256")}
    expected.update(selection={"mask_sha256": "paid"}, graph_parameters=trial.GRAPH)
    trial.check_binding(expected, expected, "complete")
    trial.check_binding(expected, expected, "quadratic")
    with pytest.raises(ValueError, match="packet"):
        trial.check_binding(dict(expected, native_sha256="another"), expected, "complete")
    with pytest.raises(ValueError, match="visit mask"):
        trial.check_binding(dict(expected, selection={"mask_sha256": "another"}), expected, "quadratic")
    with pytest.raises(ValueError, match="quadratic graph"):
        trial.check_binding(dict(expected, graph_parameters={"max_degree": 1}), expected, "quadratic")


def test_installed_control_matches_recording_offer_and_archive_with_independent_detector(trial):
    old = dict(case="south-containing", archive="shared", offer="same", source={"raw_authority": "raw"},
               native_sha256="old")
    installed = dict(case="south-containing", archive="shared", offer="same", raw_authority="raw",
                     native_sha256="new")
    trial.check_installed_binding(old, installed)
    with pytest.raises(ValueError, match="different recording"):
        trial.check_installed_binding(old, dict(installed, offer="another"))


def test_owner_comparison_separates_changed_receiver_peak_from_reassignment(trial):
    old = {"c0": [["shared", 1, "conditional", 20.], ["changed-peak", 2, "conditional", 30.],
                  ["same", 3, "conditional", 100.], ["old-only", 3, "conditional", 200.]]}
    paid = {"c0": [["shared", 2, "predictive", 20.], ["changed-peak", 4, "predictive", 40.],
                   ["same", 3, "conditional", 100.], ["new-only", 4, "conditional", 300.]]}
    changes = trial.matched_owners(old, paid)
    assert changes["c0"] == dict(shared_visits=3, shared_same_cfo=2, reassigned_same_cfo=1,
                                role_changes_same_cfo=1, lost=1, new=1)
    assert all(count == 0 for count in changes["fitted_c"].values())


def test_projection_keeps_acquisition_outside_call_cost_and_charges_selector_and_solve(trial):
    old = dict(ledger={"acquisition_cpu_s": 9.}, replay={"all_native_cpu_s": 6.})
    paid = dict(paid_native_cpu_s=2., selection_cpu_s=.25)
    assert trial.projected_cpu(old, paid, solve_cpu=4.) == 9.25


def test_exterior_requires_original_two_receiver_decision(trial):
    assert trial.actual_exterior(dict(status="withheld", reason="both_receivers_support_far_exterior"))
    assert not trial.actual_exterior(dict(status="withheld", reason="no_active_curvature"))
    assert not trial.actual_exterior(dict(status="failed", reason="both_receivers_support_far_exterior"))
