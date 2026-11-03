import numpy as np

from probe_ds23_linear_family_groups import candidate_groups


def track(key,receiver,channel,start,stop):
    return dict(key=key,receiver=receiver,channel=channel,times=np.linspace(start,stop,9),
                observation_ids=[key+str(i) for i in range(9)])


def test_grouping_is_based_on_time_and_distinct_owners_without_using_satellite_labels():
    rows=[track('a',1,1,0,10),track('b',2,1,8,18),track('c',1,2,25,35),track('far',2,2,100,110)]
    groups=candidate_groups(rows,[],set())
    assert (0,1) in groups and (1,2) in groups and (0,1,2) in groups
    assert all(3 not in g for g in groups)


def test_groups_exclude_accepted_curved_and_duplicate_physical_measurements():
    rows=[track('a',1,1,0,10),track('b',2,1,0,10)]
    assert not candidate_groups(rows,[0],set())
    assert not candidate_groups(rows,[],{rows[0]['observation_ids'][0]})
    rows[1]['observation_ids'][0]=rows[0]['observation_ids'][0]
    assert not candidate_groups(rows,[],set())
