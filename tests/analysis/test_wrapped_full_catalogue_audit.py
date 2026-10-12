import numpy as np
import pytest

from tools.audit_wrapped_full_catalogue import common_seed, embed_incumbent


def test_full_catalogue_embedding_preserves_physical_identity_and_learned_weights():
    fit = dict(
        active=[1, 0],
        norad=[30, 10],
        full_catalogue_indices=[2, 0],
        satellite_phase_s=[0.2, -0.3],
        weights=[0.1, 0.6, 0.3],
        beta=[1, 2, 3, 4, 5, 6, -600],
        coefficient_enabled=True,
        coefficient_hz_ghz=-600,
        phase_s=0.4,
        satellite_bias_hz=[100, -200],
    )
    embedded = embed_incumbent(fit, [10, 30], np.array([10, 20, 30, 40]))
    assert embedded["active"] == [2, 0]
    assert embedded["satellite_phase_s"] == [0.2, 0, -0.3, 0]
    assert embedded["weights"] == fit["weights"]
    assert embedded["satellite_bias_hz"] == [100, 0, -200, 0]
    assert common_seed(embedded)["beta"] == fit["beta"][:-1]
    for changed in (dict(fit, norad=[10, 30]), dict(fit, full_catalogue_indices=[0, 2])):
        with pytest.raises(ValueError, match="changed"):
            embed_incumbent(changed, [10, 30], [10, 20, 30, 40])
    with pytest.raises(ValueError, match="absent"):
        embed_incumbent(fit, [10, 30], [10, 20])
