from probe_iteration018_conflicts import eligible_targets,single_source_group


def test_existing_source_not_readded_and_candidate_bound():
    candidates=[dict(qualified=True,conditional_RMS_hz=200,norad=k) for k in range(5)]
    targets=[dict(target=dict(component=n),candidates=candidates) for n in ('active','unused','other','extra')]
    selected=eligible_targets(targets,{'active'})
    assert [t['target']['component'] for t,_ in selected]==['unused','other']
    assert all(len(c)==3 for _,c in selected)


def test_expanded_family_requires_failed_single_active_identity():
    def trial(indices,valid=False):
        return dict(paired_valid=valid,additions=[dict(candidate_index=j,component=str(k)) for k,j in enumerate(indices)],added_curved_points=20)
    good=trial([2]);bad=[trial([2],True),trial([7]),trial([2,3])]
    assert single_source_group(bad,{2,3}) is None
    assert single_source_group(bad+[good],{2,3}) is good
