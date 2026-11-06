import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_joint_chunks import candidate, ordered_chunks

from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from tests.analysis.test_joint_predictive_families import fixture


@pytest.mark.parametrize('workers', [1, 2, 3])
@pytest.mark.parametrize('optimized', [True, False])
@pytest.mark.parametrize('kind', ['regular', 'invisible', 'ties'])
def test_chunks_preserve_every_field_and_input_with_invisible_and_tied_maps(
        workers, optimized, kind):
    inputs = fixture()
    if kind == 'invisible':
        inputs[-1][0][:] = False
    elif kind == 'ties':
        for array in inputs[1] + inputs[3]:
            array[:] = array[:1]
        for array in inputs[4]:
            array[:] = 0.
    before = fingerprint(inputs)
    fn, _ = candidate(workers=workers)
    for chunk in (4, 32768):
        args = dict(max_pairs=chunk, optimize_contractions=optimized)
        assert fingerprint(fn(*inputs, **args)) == fingerprint(
            two_family_phase_evidence(*inputs, **args))
    assert fingerprint(inputs) == before


def test_chunk_worker_error_cannot_become_partial_scientific_result():
    def failing(i):
        if i == 1:
            raise np.linalg.LinAlgError('singular')
        return i
    with pytest.raises(np.linalg.LinAlgError, match='singular'):
        list(ordered_chunks(failing, range(4), workers=3))


def test_chunk_boundary_and_capacity_fail_closed():
    with pytest.raises(ValueError, match='boundary'):
        candidate(workers=3, source='def f(): return 0')
    with pytest.raises(ValueError, match='slots'):
        candidate(workers=4)
