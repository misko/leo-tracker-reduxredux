import pytest
import run_full as run


def test_incomplete_bank_is_not_a_scientific_rejection():
    assert run.inherited_exception({'status': 'deadline_fallback'}, {'status': 'failed', 'trials': []}) == 'frozen_bank_incomplete'
    assert run.inherited_exception({'status': 'complete'}, {'status': 'complete', 'trials': []}) is None
    assert run.inherited_exception({'status': 'reference_unqualified'}, None) == 'reference_unqualified'


def cov(ids):
    return {a: dict(accepted_observation_ids=ids, associated=len(ids), total_GLRT=3, percent=100*len(ids)/3) for a in run.ARMS}


def test_coverage_rejects_duplicate_or_nonphysical_ids():
    run.check_ids(cov(['a', 'b']), {'a', 'b', 'c'})
    with pytest.raises(AssertionError, match='duplicate'): run.check_ids(cov(['a', 'a']), {'a', 'b', 'c'})
    with pytest.raises(AssertionError, match='nonphysical'): run.check_ids(cov(['a', 'x']), {'a', 'b', 'c'})


def test_both_arms_must_preserve_original_membership():
    original = cov(['a', 'b']); child = cov(['a', 'b', 'c'])
    assert run.exp.preserve(original, child)
    child['fitted_c']['accepted_observation_ids'] = ['a', 'c']
    assert not run.exp.preserve(original, child)
