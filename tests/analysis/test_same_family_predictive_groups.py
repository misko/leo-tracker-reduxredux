import pytest
from run_same_family_predictive_groups import build_groups


def record(scan,track,norad=123):
    return dict(job=dict(job_id=scan),track_id=track,norad=norad,validation=track)


def test_same_satellite_in_different_scans_does_not_share_nuisance_parameters():
    groups=build_groups([record('a','1'),record('a','2'),record('b','3'),record('b','4')])
    assert len(groups)==2 and {g['job']['job_id'] for g in groups}=={'a','b'}
    with pytest.raises(ValueError):build_groups([record('a','1'),record('b','2')])


def test_duplicate_curve_cannot_be_counted_twice_or_assigned_two_group_labels():
    with pytest.raises(ValueError):build_groups([record('a','1'),record('a','1')])
    with pytest.raises(ValueError):build_groups([record('a','1'),record('a','2'),record('a','1',124),record('a','3',124)])
