"""Only the proven screen ancestry may be composed; the exact kernel is preserved."""

import pytest
from evaluate_integer_epoch_pair import MEMBERS, PREFIX, replacements


def inventories():
    names = ['_native_acquisition.c', *MEMBERS]
    original = {PREFIX+n: 'old-'+n for n in names}
    base = {PREFIX+'_screen_native/'+n: 'old-'+n for n in names}
    probe = {**original, **{PREFIX+n: 'new-'+n for n in MEMBERS}}
    return base, probe, original


def test_only_screen_grid_and_binary_are_replaced():
    actual = replacements(*inventories())
    assert set(actual) == {PREFIX+'_screen_native/'+n for n in MEMBERS}
    assert all('_screen_native' in p for p in actual)


@pytest.mark.parametrize('side', [0, 1])
def test_other_screen_ancestry_or_unrelated_probe_change_rejected(side):
    rows = inventories()
    name = PREFIX+('_screen_native/' if side == 0 else '')+'_native_acquisition.c'
    rows[side][name] = 'unexpected'
    with pytest.raises(ValueError):
        replacements(*rows)
