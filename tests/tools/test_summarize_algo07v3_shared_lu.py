import pytest
from summarize_algo07v3_shared_lu import kernel_totals, stage_totals


def test_nested_kernel_clocks_remain_separate_by_contraction_mode():
    result = kernel_totals([
        dict(optimized=True, seconds=2., phase_pairs=100),
        dict(optimized=False, seconds=3., phase_pairs=50),
        dict(optimized=True, seconds=4., phase_pairs=200),
    ])
    assert result == dict(optimized=dict(calls=2, seconds=6., phase_pairs=300),
                          direct=dict(calls=1, seconds=3., phase_pairs=50))
    with pytest.raises(ValueError):
        kernel_totals([])


def test_stage_reader_excludes_nested_events_and_refuses_duplicate_stages(tmp_path):
    path = tmp_path / 'worker.log'
    path.write_text('diagnostic text\n'
                    '{"event":"stage","stage":"predictive","seconds":100}\n'
                    '{"event":"recovery_stage","stage":"joint-c0","seconds":20}\n')
    assert stage_totals(path) == {'predictive': 100}
    with path.open('a') as stream:
        stream.write('{"event":"stage","stage":"predictive","seconds":101}\n')
    with pytest.raises(ValueError, match='Duplicate'):
        stage_totals(path)
