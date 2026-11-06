import hashlib

import numpy as np
import pytest
from benchmark_algo07v3_direct_grids import load_capture, select_functions
from check_algo07v3_scan_likelihood import fingerprint

from tests.analysis.test_joint_predictive_families import fixture


def test_native_capture_round_trip_is_bound_to_file_and_original_array_bytes(tmp_path):
    inputs = fixture()
    folder = tmp_path / 'captures'
    folder.mkdir()
    arrays = dict(base_covariance=inputs[2])
    for name, values in zip(('observed', 'means', 'modes', 'log_priors', 'visible'),
                            (inputs[0], inputs[1], inputs[3], inputs[4], inputs[5]), strict=True):
        arrays.update({f'{name}_{i}': v for i, v in enumerate(values)})
    path = folder / '12.npz'
    np.savez(path, **arrays)
    record = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), input=fingerprint(inputs))
    assert fingerprint(load_capture(tmp_path, '12', record)) == record['input']
    with pytest.raises(ValueError, match='input bytes'):
        load_capture(tmp_path, '12', dict(record, input=[]))
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='file changed'):
        load_capture(tmp_path, '12', record)


def test_owned_variant_compares_original_factorization_with_real_backend():
    baseline, candidate, paths, workers = select_functions('owned-lu')
    assert workers == 1
    assert any('_joint_lu' in str(p) and p.suffix == '.so' for p in paths)
    inputs = fixture()
    assert fingerprint(baseline(*inputs, optimize_contractions=False)) == fingerprint(
        candidate(*inputs, optimize_contractions=False))


def test_unknown_variant_is_rejected():
    with pytest.raises(ValueError, match='variant'):
        select_functions('unknown')
