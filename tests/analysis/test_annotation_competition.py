import copy
import pytest
from review_annotation_competition import matched_expansion


def result():
    score = dict(negative_twice_log_density=20., rms_hz=100.)
    p = dict(norad=123, alias=0, arms={a: dict(scores={'conditional_target': score.copy()}) for a in ('c0', 'fitted_c')})
    return dict(track_id='target', folds=[dict(seed=1, split={'held_blocks': [2]}, proposals=[p])])


def test_expansion_keeps_original_competitor_scores_and_splits():
    old = result(); new = copy.deepcopy(old)
    extra = copy.deepcopy(new['folds'][0]['proposals'][0]); extra['norad'] = 456
    new['folds'][0]['proposals'].append(extra)
    assert matched_expansion(old, new) == [dict(seed=1, original=1, expanded=2)]


@pytest.mark.parametrize('change', ['split', 'score', 'alias', 'missing', 'target'])
def test_changed_controls_are_rejected(change):
    old = result(); new = copy.deepcopy(old); f = new['folds'][0]
    if change == 'split': f['split']['held_blocks'] = [3]
    if change == 'score': f['proposals'][0]['arms']['fitted_c']['scores']['conditional_target']['rms_hz'] = 90.
    if change == 'alias': f['proposals'][0]['alias'] = 1
    if change == 'missing': f['proposals'] = []
    if change == 'target': new['track_id'] = 'other'
    with pytest.raises(ValueError): matched_expansion(old, new)
