import copy
from resume_ds23_large_joint_search import node_key


def test_alias_or_family_change_cannot_reuse_another_proposal_fit():
    node=dict(seed=dict(rows=[dict(candidate_index=10),dict(candidate_index=20)]),aliases=[0,1])
    cached={node_key(node):'fit'}
    changed=copy.deepcopy(node);changed['aliases'][1]=2
    assert node_key(changed) not in cached
    changed=copy.deepcopy(node);changed['seed']['rows'][1]['candidate_index']=21
    assert node_key(changed) not in cached


def test_fragment_order_is_part_of_checkpoint_identity():
    a=dict(seed=dict(rows=[dict(candidate_index=10),dict(candidate_index=20)]),aliases=[0,1])
    b=dict(seed=dict(rows=list(reversed(a['seed']['rows']))),aliases=list(reversed(a['aliases'])))
    assert node_key(a)!=node_key(b)
