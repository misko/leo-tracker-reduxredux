import json
from types import SimpleNamespace

import pytest
from compare_algo07_star_publication import presentation_document, run, science_document


def test_only_validated_top_level_accounting_is_removed():
    source = dict(replay_seconds=1., terminal_sha256='binding', artifacts=[],
                  arms=dict(c0=dict(seconds=4., owner_sha256='owners', endpoint_latlon=[1., 2.])))
    result = science_document(source)
    assert result == dict(arms=source['arms'])
    assert source['replay_seconds'] == 1.
    with pytest.raises(ValueError, match='accounting'):
        science_document(dict(source, replay_seconds=float('nan')))


def test_grid_scores_and_ownership_binding_are_retained():
    grid = dict(binding=dict(terminal_sha256='binding', owner_sha256='owners',
                             position_png_sha256='png'), elapsed_seconds=2., complete=True,
                points=[dict(scores=dict(c0=3., fitted_c=4.))])
    result = presentation_document(grid, grid=True)
    assert result['points'] == grid['points']
    assert result['binding'] == dict(owner_sha256='owners', position_png_sha256='png')
    with pytest.raises(ValueError, match='Incomplete'):
        presentation_document(dict(grid, complete=False), grid=True)


def publication_args(tmp_path):
    values = dict(run_id='scan', output=tmp_path/'comparison.json')
    for key in ('reference', 'candidate', 'reference_publication', 'candidate_publication'):
        values[key] = tmp_path/key
        values[key].mkdir()
        if key in ('reference', 'candidate'):
            (values[key]/'algo07-star-input.json').write_text(json.dumps(
                dict(kind='algo07-star-native-evidence', run_id='scan')))
    return SimpleNamespace(**values)


def test_separate_publication_store_still_requires_exact_source_terminal(tmp_path, monkeypatch):
    args = publication_args(tmp_path)
    seen = []

    def target(root):
        seen.append(root)
        return SimpleNamespace(detail=lambda run_id:
                               dict(state='complete', terminal_sha256='wrong'))

    monkeypatch.setattr('compare_algo07_star_publication.FastStandardAnalysisStore', target)
    monkeypatch.setattr('compare_algo07_star_publication.FastGraphPositionStoreV6', lambda root:
        SimpleNamespace(completed_jobs=lambda: [dict(run_id='scan')],
                        terminal=lambda job: ({}, {'sha256': 'correct'})))
    with pytest.raises(ValueError, match='another scientific terminal'):
        run(args)
    assert seen == [args.reference_publication]


def test_shared_publication_store_is_rejected(tmp_path):
    args = publication_args(tmp_path)
    args.candidate_publication = args.reference_publication
    with pytest.raises(ValueError, match='Independent publication stores'):
        run(args)
