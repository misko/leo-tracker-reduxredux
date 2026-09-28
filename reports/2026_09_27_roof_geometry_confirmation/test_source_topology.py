from dataclasses import dataclass
import pytest
from source_topology import filter_prepared


@dataclass(frozen=True)
class Track:
    track_id: str
    observation_ids: tuple
    training_mask: tuple


@dataclass(frozen=True)
class Prepared:
    tracks: tuple


def test_excludes_both_collision_tracks_not_just_one_receiver_row():
    p=Prepared((Track('a',('x',),(False,)),Track('b',('y',),(True,)),Track('c',('z',),(False,))))
    links=[dict(track_id=t,observation_id=o,candidate_ids=[c]) for t,o,c in [('a','x','shared'),('b','y','shared'),('c','z','unique')]]
    filtered,receipt=filter_prepared(p,links)
    assert [t.track_id for t in filtered.tracks]==['c']
    assert receipt['removed_track_ids']==['a','b']
    assert receipt['counts']['cross_split_source_anchors']==1
    assert len(p.tracks)==3


def test_clean_inputs_preserve_exact_original_object():
    p=Prepared((Track('a',('x','y'),(True,False)),))
    links=[dict(track_id='a',observation_id=o,candidate_ids=[o]) for o in ('x','y')]
    filtered,receipt=filter_prepared(p,links)
    assert filtered is p and receipt['unchanged']


def test_ambiguous_links_fail_closed():
    p=Prepared((Track('a',('x',),(True,)),))
    with pytest.raises(ValueError,match='uniquely'):
        filter_prepared(p,[dict(track_id='a',observation_id='x',candidate_ids=['one','two'])])
