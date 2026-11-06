import hashlib
from pathlib import Path

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_posterior_buffers import candidate_function, reference


@pytest.mark.parametrize('variant', ['metadata', 'buffers'])
@pytest.mark.parametrize('width', [0, 1, 16, 190])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('density', [0., .2, 1.])
def test_complete_bound_and_inputs_exact(variant, width, layout, density):
    rng = np.random.default_rng(2391)
    u = rng.normal(size=(96, width))
    u[rng.random(u.shape) >= density] = 0
    u = np.array(u, order=layout)
    y, s, g = rng.normal(size=96) * 100, rng.uniform(3, 40, 96), np.arange(96) % 5 * 3
    kwargs = dict(prior_groups=np.arange(width) // 5 - 1,
                  powers=np.linspace(.1, 1., 5), iterations=16)
    before = fingerprint((y, u, s, g, kwargs))
    operation, _, _ = candidate_function(variant)
    assert fingerprint(operation(y, u, s, g, **kwargs)) == fingerprint(
        reference.hierarchical_bound(y, u, s, g, **kwargs))
    assert fingerprint((y, u, s, g, kwargs)) == before


def test_frozen_reference_matches_measured_prebuffer_runtime():
    assert hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest() == (
        '21c5947b4888f9602365af8b4b87a58af4d6becbf1a34ca682cd0d3a63172919')


def test_unknown_variant_is_rejected():
    with pytest.raises(ValueError, match='Unknown'):
        candidate_function('unreviewed')
