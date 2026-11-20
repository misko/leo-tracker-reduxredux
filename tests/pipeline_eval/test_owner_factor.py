import numpy as np
import pytest

from tools.pipeline_eval.qualification import owner_factor_archive as archive
from tools.pipeline_eval.qualification import owner_factor_models as models


def test_publication_lift_requires_native_component_and_exact_rf():
    row = dict(
        observation_id="o",
        component="SCAN-RX1-CH3-T001-RF11000000000.000000",
        receiver=1,
        channel=3,
        time_s=7.42,
        measured_cfo_hz=120 + models.lean.PERIOD,
        norad=30,
        role="conditional",
        archived_residual_hz={"c0": 0.0, "fitted_c": 1.0},
    )
    native = dict(receiver=1, channel=3, time_s=7.42, measured_cfo_hz=120, actual_rf_hz=11e9)
    evidence = archive.row_factors(row, native)
    assert evidence["v5_lift"] == 1
    assert evidence["folded_hz"] == 120
    with pytest.raises(ValueError, match="component/point"):
        archive.row_factors(row, native | {"actual_rf_hz": 11.01e9})


def test_common_mask_keeps_distinct_aliases_and_keeps_validation_outside_fit():
    owner = dict(
        rx=1, channel=2, time_s=1.0, folded_hz=100.0, role="conditional", v5_owner=10, v5_lift=0
    )
    chosen = dict(receiver=1, channel=2, time_s=1.0, cfo_hz=100.0, norad=11, track=1, lean_lift=1)
    masks, counts = models.join(
        [owner, owner | {"time_s": 2}, owner | {"time_s": 3, "role": "predictive"}], [chosen]
    )
    assert len(masks["full"]) == 2 and len(masks["common"]) == 1
    assert counts["different_owner"] == counts["different_alias"] == 1
    assert counts["predictive_rows"] == 1
    assert masks["common"][0]["lean_lift"] == 1


def test_smooth_clock_basis_has_no_affine_component():
    t = np.arange(301.0)
    basis = models.clock_basis(t)
    assert basis.shape == (301, 11)
    assert np.allclose(basis.sum(axis=0), 0, atol=1e-11)
    assert np.allclose((t - 150) @ basis, 0, atol=1e-9)
