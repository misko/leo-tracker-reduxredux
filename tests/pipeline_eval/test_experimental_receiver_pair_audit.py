from tools.pipeline_eval.variants.experimental.receiver_pair_audit import audit, paired_support


def factor(epoch, hz, rank=0):
    return rank, epoch, 0., hz, .12, .04


def test_transfer_preserves_distinct_factors_and_signed_cfo():
    donor = [factor(0, -50000)]
    other = [factor(13332, -100000), factor(1, 50000, rank=1)]
    assert paired_support(donor, other, 2) == 1
    assert paired_support(donor, other, 2, 1000) == 0
    assert paired_support([], other, 2) == 0


def test_lane_audit_counts_partner_only_births_and_residuals():
    reports = audit([([], [factor(10, 100000), factor(40, -74000, rank=1)]),
                     ([factor(10, 105000)], [factor(10, 100000)])])
    for direction in ("rx0_donor", "rx1_donor"):
        assert reports[direction]["distinct_within_2_samples"] == 1
        assert reports[direction]["distinct_within_2_samples_and_1000_hz"] == 0
    assert reports["rx0_donor"]["target_factors_when_donor_empty"] == 2
    assert reports["rx0_donor"]["second_scan_with_no_phase_within_2_samples"] == 1
