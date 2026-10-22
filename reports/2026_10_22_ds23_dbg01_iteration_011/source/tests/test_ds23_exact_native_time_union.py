from types import SimpleNamespace
import numpy as np

from ds23_exact_native_time_union import exact_time_union


def test_orphan_inside_gap_and_beyond_original_last_time_have_exact_indices():
    original=SimpleNamespace(times=np.array([0.,1.,2.]),tracks=[dict(times=np.array([0.,2.])),dict(times=np.array([.5,3.]))],
        index=[np.array([0,2]),np.array([1,3])],curved=[0],rx_basis=[object(),object()])
    changed=exact_time_union(original)
    np.testing.assert_array_equal(changed.times,[0.,.5,1.,2.,3.])
    for t,ix in zip(changed.tracks,changed.index,strict=True):np.testing.assert_array_equal(changed.times[ix],t['times'])
    np.testing.assert_array_equal(original.times,[0.,1.,2.])
    assert changed.tracks is original.tracks and changed.rx_basis is original.rx_basis and changed.curved==[0]


def test_an_existing_exact_graph_grid_is_unchanged():
    original=SimpleNamespace(times=np.array([1.,2.]),tracks=[dict(times=np.array([1.,2.]))])
    changed=exact_time_union(original)
    np.testing.assert_array_equal(changed.times,original.times)
    np.testing.assert_array_equal(changed.index[0],[0,1])
