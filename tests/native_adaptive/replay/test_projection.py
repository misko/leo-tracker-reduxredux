from dataclasses import replace

import pytest

from leo.native_pipeline.projection import WindowAuthority, integer_support, project_integer_candidates


def authority():
    return WindowAuthority('capture','analysis',0,0,0,1,'lower',11200000000.,
                           2500000,50000,100,100,1700000000000000000)


def candidate(margin=.1):
    return dict(epoch=0,tracking_cfo_hz=1000.,exact_score=.2,control_score=.1,
                margin=margin,glrt_complete=1)


def test_large_counter_translation_preserves_time():
    a = authority()
    x = project_integer_candidates(a,[candidate()])[0]
    shifted = replace(a,first_counter=a.first_counter+2**60,anchor_counter=a.anchor_counter+2**60)
    assert project_integer_candidates(shifted,[candidate()])[0] == x
    assert x.observation[6] <= x.observation[7] < x.observation[8]


def test_threshold_preserves_rank_and_source_identity():
    a = authority()
    projected = project_integer_candidates(a,[candidate(.024),candidate(.025)])
    assert len(projected) == 1 and projected[0].source[5] == 1
    changed = project_integer_candidates(replace(a,analysis_digest='other'),[candidate(.024),candidate(.025)])[0]
    assert projected[0].observation[0] != changed.observation[0]
    assert projected[0].source[1] == changed.source[1]


def test_incomplete_or_nonfinite_measurements_rejected():
    c = candidate();c['glrt_complete'] = 0
    with pytest.raises(ValueError,match='incomplete'): project_integer_candidates(authority(),[c])
    c = candidate();c['tracking_cfo_hz'] = float('nan')
    with pytest.raises(ValueError,match='tracking_cfo'): project_integer_candidates(authority(),[c])


@pytest.mark.parametrize('epoch',[-1,50000,1.5])
def test_invalid_epoch(epoch):
    with pytest.raises(ValueError): integer_support(epoch,2500000,50000)


def test_support_truncates_at_probe_end():
    support = integer_support(49000,2500000,50000)
    assert support.start >= 49000 and support.end <= 50000
    assert support.start <= support.center < support.end
    assert support.moments[0:2] == (1.,0.)
    assert support.moments[2] > 0
