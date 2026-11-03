import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('projection_subset',
    Path(__file__).resolve().parents[3] / 'tools/compare_projection_subset.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_missing_rows_are_not_lossless():
    result = module.compare_lines(['header', 'a\t1'], ['header', 'a\t1', 'b\t2'], 1)
    assert result['all_emitted_rows_exact']
    assert not result['complete_exact']
    assert result['missing_reference_ids'] == ['b']


@pytest.mark.parametrize('rows', [['a\t1', 'a\t1'], ['bad'], ['\t2']])
def test_invalid_inventory_rejected(rows):
    with pytest.raises(ValueError):
        module.compare_lines(['header', *rows], ['header', 'a\t1'], 1)


def test_changed_value_and_unexpected_id_fail():
    result = module.compare_lines(['header', 'a\t2', 'c\t3'], ['header', 'a\t1'], 1)
    assert not result['all_emitted_rows_exact']
    assert result['mismatched_or_unexpected_ids'] == ['a', 'c']


def test_support_must_have_same_ordered_ids(tmp_path):
    actual, reference = tmp_path / 'actual', tmp_path / 'reference'
    for directory in (actual, reference):
        directory.mkdir()
        (directory / 'observations.tsv').write_text('header\na\t1\nb\t2\n')
        (directory / 'graph.tsv').write_text('META\nheader\na\t3\nb\t4\n')
    assert module.compare_checkpoints(actual, reference)['complete_exact']
    (actual / 'graph.tsv').write_text('META\nheader\nb\t4\na\t3\n')
    result = module.compare_checkpoints(actual, reference)
    assert result['graph.tsv']['all_emitted_rows_exact']
    assert not result['emitted_science_exact']


def test_changed_authority_header_fails():
    result = module.compare_lines(['OTHER', 'header', 'a\t1'], ['META', 'header', 'a\t1'], 2)
    assert not result['all_emitted_rows_exact']


def test_reordering_is_not_an_exact_checkpoint():
    result = module.compare_lines(['header', 'b\t2', 'a\t1'], ['header', 'a\t1', 'b\t2'], 1)
    assert result['all_emitted_rows_exact']
    assert not result['ordered_subset']
    assert not result['complete_exact']
