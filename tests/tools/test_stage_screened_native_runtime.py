"""Production composition must reject incomplete domain evidence and unrelated changes."""

import copy

import pytest
from stage_screened_native_runtime import PREFIX, screen_requirements, validate_members


def evidence():
    return [dict(summary=dict(covered=True, cases=135, prefix_values_exact=1_000_001,
                              unsupported_rejected=6, maximum_bound_fraction=.5)),
            dict(summary=dict(all_bit_exact=True, cases=54, exact_values=59670,
                              native_rejections=5)),
            dict(summary=dict(exact=True, cases=117, screened=45, complete_fallback=72,
                              screen_kind='integer_vnni'))]


def test_full_domain_and_actual_kernel_evidence_required():
    screen_requirements(*evidence())


@pytest.mark.parametrize('index,field,value', [(0, 'covered', False), (0, 'cases', 134),
    (0, 'maximum_bound_fraction', 1.01), (0, 'prefix_values_exact', 100),
    (0, 'unsupported_rejected', 5), (1, 'all_bit_exact', False), (1, 'native_rejections', 4),
    (2, 'exact', False), (2, 'screened', 0), (2, 'complete_fallback', 0)])
def test_incomplete_domain_evidence_rejected(index, field, value):
    rows = copy.deepcopy(evidence())
    rows[index]['summary'][field] = value
    with pytest.raises(ValueError):
        screen_requirements(*rows)


def inventory():
    additions = {PREFIX+n for n in ('coarse_screen.py', '_screen_bounds.py', '_screen_exact.py',
                                    '_screen_selection.py', '_screen_integer.py')}
    additions |= {PREFIX+d+'/'+n for d in ('_screen_native', '_sparse_native')
                  for n in ('__init__.py', '_native_acquisition.c', '_native_acquisition_grid.inc',
                            '_native_acquisition.cpython-312-x86_64-linux-gnu.so')}
    original = {PREFIX+'acquisition.py': 'old', PREFIX+'_native_acquisition.so': 'original',
                'src/leo/scanner/worker.py': 'original'}
    candidate = dict(original, **{n: 'new' for n in additions})
    candidate[PREFIX+'acquisition.py'] = 'new'
    build = dict(additions=sorted(additions), changes=[PREFIX+'acquisition.py'],
                 screen_kind='integer_vnni')
    return original, candidate, build


def test_full_original_kernel_and_unrelated_members_preserved():
    validate_members(*inventory())
    for name in (PREFIX+'_native_acquisition.so', 'src/leo/scanner/worker.py'):
        original, candidate, build = inventory()
        candidate[name] = 'unexpected'
        with pytest.raises(ValueError):
            validate_members(original, candidate, build)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'wrong-kind'])
def test_missing_or_unexpected_extension_rejected(mutation):
    original, candidate, build = inventory()
    if mutation == 'missing':
        candidate.pop(PREFIX+'_sparse_native/_native_acquisition.c')
    elif mutation == 'extra':
        candidate[PREFIX+'surprise.py'] = 'new'
    else:
        build['screen_kind'] = 'fp32'
    with pytest.raises(ValueError):
        validate_members(original, candidate, build)
