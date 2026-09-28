from types import SimpleNamespace as C
import math
import pytest
import pairing as p
from prepare import select_subset, validate_pose, digest, canonical


def candidate(cfo=0, margin=.1, rank=0, epoch=0):
    return C(fractional_tracking_cfo_hz=cfo, fractional_margin=margin,
             candidate_rank=rank, integer_epoch_sample=epoch,
             fractional_epoch_offset_samples=0, passed_fractional_margin_gate=True)


def test_modulo_and_swap():
    a,b = candidate(),candidate(4000,epoch=10000)
    assert p.compatible(a,b,7500000,4000)
    assert p.compatible(b,a,7500000,-4000)


def test_counterpart_chosen_by_frequency_not_strength():
    a=candidate(); weak=candidate(4001,.03,1); strong=candidate(4500,.9,2)
    r=p.counterpart(a,[strong,weak],0,2500000,4000)
    assert r['counterpart_rank']==1
    assert r['log_margin_ratio_rx1_rx0']==pytest.approx(math.log(.3))


def test_ratio_orientation_invariant():
    a,b=candidate(0,.1),candidate(4000,.2)
    assert p.counterpart(a,[b],0,2500000,4000)['log_margin_ratio_rx1_rx0']==pytest.approx(p.counterpart(b,[a],1,2500000,4000)['log_margin_ratio_rx1_rx0'])


def test_no_counterpart_is_not_zero_margin_ratio():
    r=p.counterpart(candidate(),[],0,2500000,4000)
    assert not r['matched'] and r['log_margin_ratio_rx1_rx0'] is None


def test_subset_time_order_not_input_order_or_quality():
    poses=[dict(session_id=str(i),capture_start_earliest_utc_ns=i) for i in reversed(range(15))]
    x=select_subset(poses)
    assert [q['pose']['session_id'] for q in x]==list(map(str,range(3,15)))
    assert [q['split'] for q in x]==['calibration']*8+['holdout']*4


def test_pose_digest_fails_closed():
    a=dict(valid_from_utc_ns=0,valid_until_utc_ns=100)
    p0=dict(pose_authority=a,pose_authority_digest=digest(canonical(a)),capture_start_earliest_utc_ns=10,capture_end_utc_ns=20)
    p0['binding_digest']=digest(canonical(p0));validate_pose(p0)
    p0['capture_end_utc_ns']=30
    with pytest.raises(ValueError):validate_pose(p0)
