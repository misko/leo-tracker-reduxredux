from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_new_family_anchor_only import restrict_refinements


def test_only_required_physical_anchors_change_and_sources_are_not_mutated():
    old = [dict(key='a', observation_ids=['a1', 'a2'], values=np.array([1., 2.])),
           dict(key='b', observation_ids=['b1'], values=np.array([3.]))]
    refined = [dict(old[0], values=np.array([10., 20.])), dict(old[1], values=np.array([30.]))]
    result = restrict_refinements(old, refined, ['a2'])
    np.testing.assert_array_equal(result[0]['values'], [1., 20.])
    np.testing.assert_array_equal(result[1]['values'], [3.])
    np.testing.assert_array_equal(old[0]['values'], [1., 2.])
    np.testing.assert_array_equal(refined[0]['values'], [10., 20.])


def test_missing_conditional_anchor_cannot_be_silently_ignored():
    tracks = [dict(key='a', observation_ids=['a1'], values=np.array([1.]))]
    with pytest.raises(ValueError, match='absent'):
        restrict_refinements(tracks, tracks, ['different_physical_peak'])
