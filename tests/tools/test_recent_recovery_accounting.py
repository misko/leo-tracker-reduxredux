from audit_recent_recovery_accounting import compare


def test_preserved_postfit_points_are_not_reported_as_curved_evidence():
    old={'gates':{'tracks':[{'component':'target','norad':1,'observation_ids':['a','b']}]},
         'proposed_associated_ids':['a','b','extension']}
    new={'gates':{'tracks':[{'component':'target','norad':1,'observation_ids':['a']}]},
         'proposed_associated_ids':['a','b','extension']}
    result=compare(old,new,'target')
    assert result['target_confirmed']==2
    assert result['target_in_curved_likelihood']==1
    assert result['old_confirmed_missing']==0
    assert result['same_identity']


def test_dropped_target_is_not_silently_preserved_by_other_points():
    old={'gates':{'tracks':[{'component':'target','norad':1,'observation_ids':['a','b']}]},
         'proposed_associated_ids':['a','b','extension']}
    new={'gates':{'tracks':[]},'proposed_associated_ids':['extension','other']}
    result=compare(old,new,'target')
    assert result['target_confirmed']==result['target_in_curved_likelihood']==0
    assert result['old_confirmed_missing']==2
    assert not result['same_identity']
