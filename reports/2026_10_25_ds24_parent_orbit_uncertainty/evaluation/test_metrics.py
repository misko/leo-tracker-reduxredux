"""Evaluation failures, denominator and RF-only fallback controls."""

import math
import pytest
from metrics import ARMS, distance, local_latlon, operational_policy, research_eligible, research_policy, summarize


def test_geographically_better_unqualified_candidate_still_exact_fallback():
    reference={a:dict(endpoint_east_north_km=[0,0]) for a in ARMS}
    candidate={a:dict(endpoint_latlon=[37.849061591561885,-122.48574968092912]) for a in ARMS}
    policy,source=research_policy(reference,candidate,False)
    assert policy is reference and source=='exact_reference_fallback'


def test_paired_choice_has_no_per_arm_error_selection():
    reference={a:object() for a in ARMS};candidate={a:object() for a in ARMS}
    policy,source=research_policy(reference,candidate,True)
    assert policy is candidate and source=='candidate'
    with pytest.raises(ValueError):research_policy(reference,{'c0':object()},True)


def test_missing_endpoint_never_becomes_zero_or_a_replacement():
    summary=summarize([1.,None,3.,4.],[2.,2.,2.,4.])
    assert summary['selected']==4 and summary['available']==3 and summary['missing']==1
    assert summary['mean_km']==8/3 and summary['paired_available']==3
    assert (summary['improved'],summary['worsened'],summary['unchanged'])==(1,1,1)


def test_same_endpoint_and_common_report_distance_convention():
    point=(37.2,-122.7)
    assert distance(point,point)==0
    assert math.isclose(distance((0,1),(0,0)),6371*math.pi/180,rel_tol=1e-14)
    assert local_latlon([0.,0.])==(37.906,-122.545)


def test_nonfinite_saved_position_is_rejected():
    with pytest.raises(ValueError):local_latlon([float('nan'),0.])
    with pytest.raises(ValueError):distance([float('inf'),0.])


def test_accepted_ID_loss_blocks_research_despite_passing_gates():
    assert research_eligible(True,True,True,True)
    assert not research_eligible(True,True,False,True)
    assert not research_eligible(True,False,True,True)
    assert not research_eligible(True,True,True,False)


def test_operational_reference_stays_fixed_even_if_research_candidate_eligible():
    reference={a:object() for a in ARMS};candidate={a:object() for a in ARMS}
    assert research_policy(reference,candidate,True)[0] is candidate
    assert operational_policy(reference)[0] is reference
