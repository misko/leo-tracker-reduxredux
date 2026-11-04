import pytest
from compare_algo07_star_publication import presentation_document, science_document


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
