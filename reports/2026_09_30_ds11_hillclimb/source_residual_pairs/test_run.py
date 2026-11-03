import importlib.util
from pathlib import Path

import numpy as np

spec=importlib.util.spec_from_file_location('source_pair_test',Path(__file__).with_name('run.py'))
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_matching_is_mutual_unique_bounded_and_ties_use_first():
    assert run.match_times([0.,.1,1.],[.05,1.2,3.]) == [(0,0),(2,1)]
    assert run.match_times([], [1.]) == []
    assert run.match_times([0.], [.251]) == []


def test_constant_offsets_cancel_and_opposite_patterns_separate():
    a=np.arange(8.)
    same=run.pair_statistics(a,a+10000)
    opposite=run.pair_statistics(a,10000-a)
    assert same['differential_component_rms_hz']==0
    assert opposite['common_component_rms_hz']==0
    assert abs(same['pearson']-1)<1e-12 and abs(opposite['pearson']+1)<1e-12
    assert run.pair_statistics(a[:5],a[:5]) is None
