"""Check the archive-only aperture comparator and oracle counts."""

import pytest

from reports.ALGO08.v3.aperture_factor_union import counts, joint_rows, lane_key, matches


def factor(rank=0, sample=1, offset=0., cfo=-1_000., margin=.08):
    return [rank, sample, offset, cfo, margin, 0.]


def test_match_wraps_pilot_alignment_and_preserves_signed_carrier():
    original = factor(sample=13_332, cfo=-1000.)
    assert matches(factor(sample=0, cfo=-750.), original)
    assert not matches(factor(sample=0, cfo=750.), original)


def test_oracle_can_recover_a_match_that_margin_selection_misses():
    original = factor()
    wrong = factor(cfo=-2000., margin=.50)
    report = counts([dict(stock=[original], prefix=wrong, distributed=original)], ("distributed",))
    for row in report["results"].values():
        assert row["match_counts"]["prefix_plus_distributed"] == 1
        assert row["highest_observed_margin"]["prefix_plus_distributed"] == 0


def test_join_requires_original_iq_and_full_factor_reference():
    metadata, iq, f = {"visit_index": 4, "receiver_id": 1}, "data", factor()
    original = {lane_key(metadata, iq): dict(mode="short_primary", stock=[f], prefix=f, distributed=f)}
    row = dict(metadata=metadata, iq_sha256=iq, installed=[f], prefix=[f], centered=[f], mode="short_primary")
    assert joint_rows(original, [row])[0]["centered"] == f
    with pytest.raises(ValueError, match="unbound"):
        joint_rows(original, [dict(row, iq_sha256="different")])
    with pytest.raises(ValueError, match="installed factors"):
        joint_rows(original, [dict(row, installed=[])])
