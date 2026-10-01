from copy import deepcopy
import pytest
from materialize_first_start import first_start_receipt


def original():
    fits = [dict(seed_index=0, objectives=[20.], converged=False, seconds=4., mean=[1., 2.]),
            dict(seed_index=1, objectives=[10.], converged=True, seconds=3., mean=[3., 4.])]
    return dict(fits=fits, best=fits[1], config={'seed_limit': 3},
                wall_seconds=30., cpu_seconds=29.)


def test_first_start_kept_even_when_unresolved_and_other_start_is_better():
    source = original()
    before = deepcopy(source)
    result = first_start_receipt(source, 'parent.json', 'sha256:example')
    assert source == before
    assert result['best'] == source['fits'][0]
    assert result['status'] == 'unresolved'
    assert result['wall_seconds'] is None
    assert result['replay']['recorded_later_fit_seconds'] == 3.
    result['best']['mean'][0] = 99.
    assert source == before


def test_missing_fit_is_failure_and_nonzero_first_index_rejected():
    source = original()
    source['fits'] = []
    result = first_start_receipt(source, 'parent.json', 'sha256:example')
    assert result['best'] is None and result['status'] == 'unresolved'
    source = original()
    source['fits'][0]['seed_index'] = 1
    with pytest.raises(ValueError):
        first_start_receipt(source, 'parent.json', 'sha256:example')
