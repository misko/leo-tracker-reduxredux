import importlib.util
from pathlib import Path
import numpy as np

P = Path(__file__).with_name("run.py")
S = importlib.util.spec_from_file_location("fixed_cone_test_subject", P)
RUN = importlib.util.module_from_spec(S); S.loader.exec_module(RUN)

def test_fold_is_whole_norad_and_order_independent():
    ids = list(range(25)) + [3, 3, 12]
    assert RUN.fold_map(ids) == RUN.fold_map(ids[::-1])
    assert set(RUN.fold_map(ids).values()) == set(range(5))

def test_global_fold_map_is_stable_across_cell_subsets():
    global_map = RUN.fold_map(range(30))
    a, b = [1, 4, 9, 21], [1, 9, 17, 29]
    assert [global_map[x] for x in a if x in b] == [global_map[x] for x in b if x in a]

def test_shuffle_preserves_each_scan_lane_label_count():
    labels=np.array([0,0,1,1,0,1,0]); strata=np.array(["a"]*4+["b"]*2+["c"])
    for p in range(20):
        out, unchanged, moved=RUN.shuffled_labels(labels,strata,p)
        assert unchanged == 1 and moved == np.count_nonzero(out != labels)
        for key in set(strata):
            np.testing.assert_array_equal(np.sort(out[strata==key]),np.sort(labels[strata==key]))

def test_boolean_threshold_and_duration_weighted_selection():
    coverage=np.array([[1,0,1,0],[0,1,0,1]],dtype=bool)
    weights=np.array([5.,1.,2.,9.]); train=np.array([1,1,1,0],dtype=bool)
    assert RUN.select_orientation(coverage,weights,train) == (0,7.0)

def test_held_rows_cannot_change_selected_orientation():
    coverage=np.array([[1,0,0,0],[0,1,1,1]],dtype=bool); weights=np.ones(4)
    train=np.array([1,0,0,0],dtype=bool)
    assert RUN.select_orientation(coverage,weights,train)[0] == 0
    changed=coverage.copy(); changed[:,~train]=~changed[:,~train]
    assert RUN.select_orientation(changed,weights,train)[0] == 0

def test_twenty_degree_axes_make_tangent_ten_degree_caps():
    cone=RUN.load(RUN.CONE,"fixed_cone_geometry_test")
    axes=cone.axes(0,0,0)
    separation=np.degrees(np.arccos(np.clip(axes[0]@axes[1],-1,1)))
    np.testing.assert_allclose(separation,20.0,atol=1e-10)
    np.testing.assert_allclose(separation,2*RUN.WIDTHS[0],atol=1e-10)
