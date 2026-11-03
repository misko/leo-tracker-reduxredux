from types import SimpleNamespace

import numpy as np
from coherent_fit import anchor_partition, frozen_identity_masses


def test_anchor_partition_removes_overlap_and_keeps_group_identity():
    data = SimpleNamespace(
        times=np.arange(8, dtype=float),
        group=np.array([4, 4, 5, 6, 7, 8, 9, 10]),
        tracks=[
            {"rows": np.arange(6), "candidate_indices": [0, 1]},
            {"rows": np.arange(3, 8), "candidate_indices": [1, 2]},
        ],
    )
    anchors = anchor_partition(data, min_groups=2, min_span_s=1)
    assert len(anchors) == 2
    np.testing.assert_array_equal(anchors[0]["groups"], [4, 5, 6, 7, 8])
    np.testing.assert_array_equal(anchors[1]["groups"], [9, 10])
    assert anchors[1]["overlap_groups_removed"] == 3


def test_omitted_candidate_mass_transfers_to_unknown_not_other_satellites():
    anchors = [{"candidate_indices": np.array([0, 1])}, {"candidate_indices": np.array([9])}]
    full = frozen_identity_masses(anchors, [0, 1, 2], [0, 1, 2])
    partial = frozen_identity_masses(anchors, [0, 1, 2], [0])
    np.testing.assert_allclose(partial["raw_satellite_mass"], full["raw_satellite_mass"][:1])
    np.testing.assert_allclose(
        partial["anchor_satellite_mass"], full["anchor_satellite_mass"][:, :1]
    )
    np.testing.assert_allclose(partial["anchor_unknown_mass"], [0.6, 1])
    assert partial["raw_background_mass"] > full["raw_background_mass"]


def test_coherent_refinement_gradient_and_adapter(monkeypatch):
    import scipy.optimize
    from coherent_fit import FixedBankLikelihood
    from staged_fit import refine_bank
    from test_staged_gradient import centered_difference, synthetic_orbital_data
    from track_likelihood import prepare_track_grouped_likelihood

    data, initial = synthetic_orbital_data()
    satellites = np.array([0, 2])
    anchors = [{"candidate_indices": satellites}]
    prepared = prepare_track_grouped_likelihood(
        data.measured, data.group, row_weights=np.ones(4), anchors=[np.array([7, 2])]
    )
    likelihood = FixedBankLikelihood(
        prepared, frozen_identity_masses(anchors, satellites, satellites)
    )
    checked = []

    def verify(fun, vector, **kwargs):
        value, gradient = fun(vector)
        numerical = centered_difference(fun, vector, np.full(len(vector), 1e-5))
        np.testing.assert_allclose(gradient, numerical, rtol=2e-4, atol=1e-3)
        checked.append(value)
        return SimpleNamespace(x=vector, success=True, message="synthetic check", nit=0)

    monkeypatch.setattr(scipy.optimize, "minimize", verify)
    result = refine_bank(data, initial, satellites, np.ones(2), likelihood)
    assert len(checked) == 1
    assert result["success"]
    assert likelihood.last_result["anchor_count"] == 1
    assert likelihood.last_result["group_count"] == 3
