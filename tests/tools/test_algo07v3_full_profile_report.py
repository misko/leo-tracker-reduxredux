"""Profile reports may alias the CLI entry point, but cannot hide source drift."""

import runpy
from pathlib import Path

import pytest

check = runpy.run_path(str(Path(__file__).resolve().parents[2] /
    'reports/2026_11_06_algo07v3_full_profile/render.py'))['profile_module_changes']


def modules():
    return ({'__main__': {'sha256': 'cli'}, '__mp_main__': {'sha256': 'cli'},
             'shared': {'sha256': 'science'}},
            {'leo.cli.algo07v3': {'sha256': 'cli'}, 'shared': {'sha256': 'science'}})


def test_identical_entry_point_aliases_pass():
    assert check(*modules(), [], []) == (set(), set())


@pytest.mark.parametrize('field', ['shared', 'leo.cli.algo07v3'])
def test_scientific_or_entry_point_drift_fails(field):
    a, b = modules()
    b[field] = {'sha256': 'changed'}
    with pytest.raises(AssertionError):
        check(a, b, [], [])


@pytest.mark.parametrize('kind', ['added', 'removed', 'declared'])
def test_other_module_changes_fail(kind):
    a, b = modules()
    if kind == 'added':
        b['unexpected'] = {'sha256': 'new'}
    if kind == 'removed':
        b.pop('shared')
    with pytest.raises(AssertionError):
        check(a, b, ['shared'] if kind == 'declared' else [], [])
