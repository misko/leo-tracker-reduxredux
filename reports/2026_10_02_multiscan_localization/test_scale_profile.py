from types import SimpleNamespace

import numpy as np
import pytest
import scale_profile as subject


def test_width_selection_uses_penalized_likelihood_with_common_seed(monkeypatch):
    data = SimpleNamespace(
        measured=np.zeros(4), times=np.arange(4), group=np.arange(4),
        rf=np.ones(4), receiver=np.zeros(4), channel=np.ones(4),
    )
    source = {"anchors": [], "trials": [
        {"satellite_indices": [0], "identity_masses": {"tag": 1}},
    ]}
    seeds = []

    def refiner(data, parameters, satellites, support, likelihood, **options):
        seeds.append(parameters.copy())
        return {"selection_score": options["sigma_hz"], "success": True}

    monkeypatch.setattr(subject, "refine_gauss_newton", refiner)
    initial = np.arange(8, dtype=float)
    result = subject.fit_scale_profile(data, source, initial, widths=[400, 100])
    assert result["score_leader"]["sigma_hz"] == 100
    assert result["score_leader"]["selection_score"] == 100 + 0.5 * np.log(4)
    np.testing.assert_array_equal(seeds[0], seeds[1])
    assert seeds[0][7] == 0
    assert initial[7] == 7


@pytest.mark.parametrize("widths", [[], [0], [np.nan], [100, 100]])
def test_invalid_widths_rejected(widths):
    with pytest.raises(ValueError, match="Widths"):
        subject.fit_scale_profile(None, None, None, widths=widths)
