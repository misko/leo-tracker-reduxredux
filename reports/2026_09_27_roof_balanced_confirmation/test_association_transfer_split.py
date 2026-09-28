import copy

import pytest

from association_transfer_split import GUARD_NS, temporal_association_split


def row(index,utc,*,training=False,group="g",start=None,end=None,opp=None,pair=None):
    start=index*100 if start is None else start;end=start+50 if end is None else end
    return {"observation_index":index,"utc_ns":utc,"training":training,
            "source_group_id":group,"sample_start":start,"sample_end":end,
            "opportunity_key":opp,"physical_pair_key":pair}


def test_whole_components_and_guard_are_deterministic():
    values=[row(0,0),row(1,10_000_000,opp="same"),row(2,20_000_000,opp="same"),
            row(3,200_000_000),row(4,400_000_000),row(5,410_000_000,pair="p"),
            row(6,420_000_000,pair="p")]
    got=temporal_association_split(values)
    assert got["midpoint_utc_ns"]==210_000_000
    assert got["twice_midpoint_utc_ns"]==420_000_000
    assert got["A_observation_indices"]==[0,1,2]
    assert got["guard_excluded_observation_indices"]==[3]
    assert got["B_observation_indices"]==[4,5,6]
    assert got["guard_ns"]==GUARD_NS and got["supported"]
    assert {row["observation_index"]:row["split_label"]
            for row in got["observation_assignments"]}=={
                0:"A",1:"A",2:"A",3:"guard",4:"B",5:"B",6:"B"}
    assert temporal_association_split(list(reversed(values)))==got


def test_training_touch_drops_entire_dependency_component():
    values=[row(0,-300_000_000,training=True,opp="x"),row(1,-250_000_000,opp="x"),
            row(2,0),row(3,400_000_000)]
    got=temporal_association_split(values)
    assert got["training_component_observation_indices"]==[0,1]
    assert got["reserve_dropped_with_training_indices"]==[1]
    assert got["counts"]["reserve_dropped_with_training"]==1


def test_overlap_is_half_open_and_only_within_source_group():
    values=[row(0,0,start=0,end=100),row(1,10,start=50,end=150),
            row(2,500_000_000,start=150,end=200),
            row(3,510_000_000,group="other",start=50,end=150,opp="z"),
            row(4,1_000_000_000,group="other",start=300,end=350,opp="z")]
    got=temporal_association_split(values,guard_ns=0)
    # 0/1 overlap; 2 merely touches 1 at the half-open boundary. Identical
    # sample intervals across source groups do not create a dependency edge.
    assert not ({0,1}&set(got["B_observation_indices"]))
    assert got["counts"]["components"]==3


def test_opportunity_and_pair_keys_union_globally_across_source_groups():
    values=[row(0,0,group="a",opp="shared"),row(1,1,group="b",opp="shared"),
            row(2,500_000_000,group="a",pair="pair"),
            row(3,500_000_001,group="b",pair="pair")]
    got=temporal_association_split(values,guard_ns=0)
    assert got["counts"]["components"]==2
    labels={x["observation_index"]:x["split_label"] for x in got["observation_assignments"]}
    assert labels[0]==labels[1] and labels[2]==labels[3]


def test_midpoint_uses_original_reserve_even_when_extreme_component_is_dropped():
    values=[row(0,-1_000_000_000,training=True,opp="drop"),
            row(1,-1_000_000_000,opp="drop"),row(2,100_000_000),row(3,200_000_000)]
    got=temporal_association_split(values,guard_ns=0)
    assert got["twice_midpoint_utc_ns"]==-800_000_000
    assert got["reserve_dropped_with_training_indices"]==[1]
    assert not got["supported"] and got["unsupported_reason"]=="empty_early_partition"


def test_epoch_nanosecond_guard_boundaries_are_exact():
    base=1_790_000_000_000_000_000;mid=base+200_000_000
    values=[row(0,base),row(1,mid-GUARD_NS-1),row(2,mid-GUARD_NS),
            row(3,mid+GUARD_NS),row(4,mid+GUARD_NS+1),row(5,base+400_000_000)]
    got=temporal_association_split(values)
    assert got["twice_midpoint_utc_ns"]==2*mid
    assert {0,1}<=set(got["A_observation_indices"])
    assert {4,5}<=set(got["B_observation_indices"])
    assert {2,3}<=set(got["guard_excluded_observation_indices"])


def test_sparse_or_guarded_track_is_explicitly_unsupported_without_relaxation():
    got=temporal_association_split([row(7,123)])
    assert not got["supported"] and got["unsupported_reason"]=="empty_both_partitions"
    assert got["guard_ns"]==GUARD_NS and got["counts"]["guard_excluded"]==1
    assert got["A_observation_indices"]==got["B_observation_indices"]==[]


def test_outcome_and_measurement_fields_cannot_change_split():
    values=[row(0,0),row(1,300_000_000),row(2,600_000_000)]
    baseline=temporal_association_split(values)
    changed=copy.deepcopy(values)
    for n,item in enumerate(changed):item.update(matched=bool(n%2),measured_hz=1e9*n,ratio=-999*n)
    assert temporal_association_split(changed)==baseline


def test_no_dependency_edge_crosses_training_A_B_or_guard():
    values=[row(0,-500_000_000,training=True,pair="train"),
            row(1,-400_000_000,pair="train"),row(2,0,opp="a"),row(3,1,opp="a"),
            row(4,500_000_000,start=1000,end=1100),row(5,500_000_001,start=1050,end=1150)]
    got=temporal_association_split(values,guard_ns=0)
    buckets=[set(got[name]) for name in ("training_component_observation_indices",
        "A_observation_indices","B_observation_indices","guard_excluded_observation_indices")]
    assert all(not buckets[i]&buckets[j] for i in range(4) for j in range(i+1,4))
    assert {0,1}<=buckets[0] and ({2,3}<=buckets[1] or {2,3}<=buckets[2])
    assert ({4,5}<=buckets[1] or {4,5}<=buckets[2])


@pytest.mark.parametrize("values",[
    [],[row(0,0),row(0,1)],[{**row(0,0),"training":1}],
    [{**row(0,0),"sample_end":0}],[{**row(0,0),"source_group_id":""}],
    [{**row(0,0),"utc_ns":.5}],[{**row(0,0),"observation_index":.5}],
    [{**row(0,0),"sample_start":.5}],
    [{**row(0,0),"observation_id":"same"},
     {**row(1,1),"observation_id":"same"}]])
def test_invalid_inputs(values):
    with pytest.raises(ValueError):temporal_association_split(values)
