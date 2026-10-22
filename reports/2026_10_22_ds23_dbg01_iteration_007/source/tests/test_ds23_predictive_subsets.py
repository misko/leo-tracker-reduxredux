from types import SimpleNamespace
import numpy as np
import pytest
from ds23_predictive_subsets import realize_predictive_subsets,assert_realized_predictive_membership


def fixture():
    track=dict(key='original',times=np.arange(5.),values=np.arange(5.)*10,observation_ids=list('abcde'),
        indices=list(range(5)),pieces=[],start_s=0.,end_s=4.)
    scan=SimpleNamespace(tracks=[track],rx_basis=[np.arange(10).reshape(5,2)],white=[object()],index=[np.arange(5)],curved=[0])
    entry=dict(track_index=0,component='original',observation_ids=list('ace'),points=3)
    return scan,entry


def test_subset_reduces_actual_rows_without_changing_any_original_track():
    scan,entry=fixture();changed,entries,receipt=realize_predictive_subsets(scan,[entry])
    assert scan.tracks[0]['observation_ids']==list('abcde') and len(scan.tracks)==1
    assert changed.tracks[0] is scan.tracks[0] and changed.curved==[0]
    t=changed.tracks[entries[0]['track_index']]
    np.testing.assert_array_equal(t['times'],[0,2,4]);np.testing.assert_array_equal(t['values'],[0,20,40])
    np.testing.assert_array_equal(changed.rx_basis[1],scan.rx_basis[0][[0,2,4]])
    assert assert_realized_predictive_membership(changed,entries,['b','d'])==list('ace')
    assert receipt[0]['omitted_ids']==list('bd')


def test_full_support_retains_identical_arrays_and_original_component():
    scan,entry=fixture();entry=dict(entry,observation_ids=list('abcde'),points=5)
    changed,entries,receipt=realize_predictive_subsets(scan,[entry])
    assert len(changed.tracks)==1 and entries==[entry] and not receipt
    assert changed.tracks[0]['values'] is scan.tracks[0]['values']


@pytest.mark.parametrize('ids,count',[(['a','a'],2),(['z'],1),(['c','a'],2),(['a'],2),([],0)])
def test_bad_subset_contracts_are_rejected(ids,count):
    scan,entry=fixture()
    with pytest.raises(ValueError):realize_predictive_subsets(scan,[dict(entry,observation_ids=ids,points=count)])


def test_metadata_only_quarantine_is_rejected():
    scan,entry=fixture()
    with pytest.raises(ValueError,match='actual numerical rows'):assert_realized_predictive_membership(scan,[entry])
