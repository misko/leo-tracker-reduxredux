"""Owned layout optimization preserves all output bytes and source observations."""

import numpy as np
import pytest

from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from tests.analysis.joint_layout_oracle import reference


@pytest.mark.parametrize('mode', [False, True])
@pytest.mark.parametrize('chunk', [1, 7, 32768])
@pytest.mark.parametrize('layout', ['strided', 'c', 'fortran', 'reversed', 'broadcast'])
@pytest.mark.parametrize('shape', [
    (1, 1, 3, 5, 3, 3), (1, 7, 3, 5, 3, 3), (7, 1, 3, 5, 3, 3),
    (4, 7, 3, 5, 3, 3), (5, 9, 7, 11, 2, 4), (17, 23, 9, 14, 3, 3),
    (2, 3, 1, 1, 1, 1), (4, 5, 1, 9, 3, 3), (4, 5, 9, 1, 3, 3),
    (2, 7, 1, 33, 3, 3), (3, 11, 1, 7, 2, 3), (7, 7, 1, 33, 6, 6),
    (2, 7, 1, 65, 3, 4), (2, 7, 1, 8, 6, 8),
])
def test_complete_bytes_and_inputs(shape, chunk, mode, layout):
    k1, k2, n1, n2, d1, d2 = shape
    rng = np.random.default_rng(304)
    h = rng.normal(size=(n1 + n2, 3))
    inputs = [[rng.normal(size=n) for n in (n1, n2)],
              [rng.normal(size=(k, n)) for k, n in ((k1, n1), (k2, n2))],
              np.eye(n1 + n2) + h @ h.T,
              [rng.normal(size=(k, n, 2 * d))[:, :, ::2]
               for k, n, d in ((k1, n1, d1), (k2, n2, d2))],
              [rng.normal(size=k) for k in (k1, k2)],
              [np.ones(k, dtype=bool) for k in (k1, k2)]]
    for index in range(2):
        if layout == 'c':
            inputs[3][index] = np.ascontiguousarray(inputs[3][index])
        elif layout == 'fortran':
            inputs[3][index] = np.asfortranarray(inputs[3][index])
            inputs[1][index] = np.asfortranarray(inputs[1][index])
        elif layout == 'reversed':
            inputs[3][index] = inputs[3][index][::-1, ::-1, ::-1]
            inputs[1][index] = inputs[1][index][::-1, ::-1]
        elif layout == 'broadcast':
            inputs[3][index] = np.broadcast_to(inputs[3][index][:1], inputs[3][index].shape)
            inputs[1][index] = np.broadcast_to(inputs[1][index][:1], inputs[1][index].shape)

    def bits(value):
        if isinstance(value, np.ndarray):
            return value.dtype.str, value.shape, value.tobytes()
        if isinstance(value, list):
            return list(map(bits, value))
        if isinstance(value, dict):
            return {key: bits(item) for key, item in value.items()}
        if isinstance(value, float):
            return np.float64(value).tobytes()
        return value

    before = bits(inputs)
    options = dict(max_pairs=chunk, optimize_contractions=mode)
    expected = reference(*inputs, **options)
    actual = two_family_phase_evidence(*inputs, **options)
    assert bits(actual) == bits(expected)
    assert bits(inputs) == before
