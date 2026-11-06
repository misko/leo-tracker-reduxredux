"""Compression exactness is probed, not assumed for floating-point inputs."""

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_inactive_columns import candidate

from leo.analysis.localization_v3 import hierarchical


@pytest.mark.parametrize('width', [0, 1, 8])
def test_all_inactive_complete_outputs(width):
    args = np.arange(8.), np.zeros((8,width)), np.ones(8), np.arange(8)%2
    operation, _, _ = candidate()
    expected = hierarchical.hierarchical_bound(*args)
    actual = operation(*args)
    assert fingerprint(actual)==fingerprint(expected)


@pytest.mark.parametrize('learned', [False, True])
def test_active_or_learned_prior_fallback(learned):
    rng = np.random.default_rng(3)
    features = rng.normal(size=(16,7))
    if learned:
        features[:,2]=0
    args = rng.normal(size=16), features, np.ones(16), np.arange(16)%3
    kw = dict(prior_groups=np.arange(7)%2 if learned else None)
    before = fingerprint((args,kw))
    operation, _, _ = candidate()
    expected = fingerprint(hierarchical.hierarchical_bound(*args, **kw))
    assert fingerprint(operation(*args, **kw)) == expected
    assert fingerprint((args,kw))==before
