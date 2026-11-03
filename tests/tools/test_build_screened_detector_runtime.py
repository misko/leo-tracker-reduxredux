"""The composition changes acquisition selection only, retaining full-grid APIs."""

import ast

import pytest
from build_screened_detector_runtime import transform

SOURCE = '''def another_function():
    return "untouched"

def acquire_symbolwise(values):
    score_maps = {}
    coarse_scores = _folded_anchor_score_grid(
        values, exact, sample_rate_hz, coarse_absolute, config.anchor_symbols, epoch_count,
    )
    for residual, scores in zip(coarse_residuals, coarse_scores, strict=True):
        score_maps[residual] = scores
    retained = _retain_score_map_peaks(
        coarse_residuals, coarse_scores, config.retained_candidate_count,
        config.candidate_epoch_separation_samples, config.candidate_cfo_separation_hz, epoch_count,
    )
    if not retained or retained[0][0] <= 0:
        return None
    return retained, score_maps

def _folded_anchor_score_grid(*args):
    return "original exact implementation"
'''


def test_only_acquisition_selection_is_replaced():
    changed = transform(SOURCE)
    before, after = ast.parse(SOURCE).body, ast.parse(changed).body
    assert ast.dump(before[0]) == ast.dump(after[0])
    assert ast.dump(before[2]) == ast.dump(after[2])
    assert '_screened_acquire' in changed
    assert 'score_maps[residual] = scores' in changed
    assert changed.split('    if not retained', 1)[1] == SOURCE.split('    if not retained', 1)[1]


@pytest.mark.parametrize('source', ['', SOURCE.replace('retained = _retain_score_map_peaks',
                                                      'retained = unknown'), transform(SOURCE)])
def test_unknown_or_already_transformed_source_rejected(source):
    with pytest.raises(ValueError):
        transform(source)
