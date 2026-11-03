import pytest
from compare_published_associations import compare


def test_same_memberships_compare_identity_offset_and_residual_separately():
    authority={'sites':[{'name':'test'}]}
    published={'priors':[{'name':'test','selected':{'capped_weighted_rmse_hz':20}}],
        'diagnostics':{'track_evidence':[{'track_id':'a'}],'selected_track_scores':{'test':[
            {'track_id':'a','candidate_id':'123','tau_s':-2,'heldout_rms_hz':20}]}}}
    native={'points':[{'score_hz':20.1,'tracks':[{'candidate_id':123,'tau_s':-2,'held_hz':20.1}]}]}
    result=compare(authority,published,native)[0]
    assert result['same_satellite']==result['same_tau']==1
    assert result['score_delta_hz']==pytest.approx(.1)
    native['points'][0]['tracks'][0]['candidate_id']=124
    assert compare(authority,published,native)[0]['same_satellite']==0
    native['points'][0]['tracks']=[]
    with pytest.raises(ValueError,match='missing comparison track'):compare(authority,published,native)
