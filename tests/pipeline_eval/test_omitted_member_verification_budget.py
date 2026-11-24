import pytest

from reports.ALGO08.v3.omitted_member_verification_budget import projection


def test_replacement_budget_adds_new_verification_after_removing_old_envelope_once():
    donor = dict(transferred_decode_hash_only_cpu_s=2, transferred_cpu_s=3, transferred_wall_s=4)
    row = projection(52, 46, 4.5, 3, donor)
    assert row["replacement_budget_s"] == pytest.approx(1.5)
    assert row["if_all_recorded_omitted_main_work_free_s"] == pytest.approx(47.5)
    assert row["modeled_wall_with_donor_decode_hash_alone_s"] == pytest.approx(46.5)
    assert row["modeled_wall_with_donor_full_verification_cpu_s"] == pytest.approx(47.5)
    assert row["modeled_wall_with_donor_full_verification_wall_s"] == pytest.approx(48.5)
