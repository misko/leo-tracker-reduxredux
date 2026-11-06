"""The external covariance policy is localized and restores thread configuration."""

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_covariance_threads import candidate, hierarchical


@pytest.mark.parametrize('width', [0, 1, 16, 175, 177])
def test_only_covariance_is_wrapped_with_configuration(width):
    rng = np.random.default_rng(61106)
    args = (rng.normal(size=80), rng.normal(size=(80, width)), 20., np.arange(80) % 4)
    settings = []
    operation, _ = candidate(lambda *args: settings.append(args), 2)
    before = fingerprint(args)
    expected = hierarchical.hierarchical_bound(*args, iterations=3)
    assert fingerprint(operation(*args, iterations=3)) == fingerprint(expected)
    assert fingerprint(args) == before
    assert settings == [('numpy', 2), ('numpy', 1)] * expected['precision_iterations']


def test_setting_failure_restores_serial_configuration():
    calls = []

    def configure(owner, threads):
        calls.append((owner, threads))
        if threads == 2:
            raise RuntimeError('configuration failed')

    operation, _ = candidate(configure, 2)
    with pytest.raises(RuntimeError, match='configuration failed'):
        operation(np.ones(5), np.ones((5, 1)), 1., np.zeros(5, dtype=int))
    assert calls == [('numpy', 2), ('numpy', 1)]
