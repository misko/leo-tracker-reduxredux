from audit_bundle_inclusion_members import qualified


def test_all_members_and_both_arms_and_replays_required_without_overriding_whole_group_failure():
    members=[dict(track_id='a'),dict(track_id='b')]
    rows=[dict(arm=a,kind=k,member=m['track_id'],passed=True) for a in ('c0','fitted_c') for k in ('nominal','continuous') for m in members]
    assert qualified(True,True,True,True,rows,members)
    assert not qualified(True,False,True,True,rows,members)
    assert not qualified(True,True,True,True,rows[:-1],members)
    assert not qualified(True,True,True,True,rows+[rows[0]],members)
    assert not qualified(True,True,True,True,[dict(r,passed=False) if i==0 else r for i,r in enumerate(rows)],members)
