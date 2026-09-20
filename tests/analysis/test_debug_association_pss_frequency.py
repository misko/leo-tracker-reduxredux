"""Scientific diagnostic invariants, without storage or hardware."""

import numpy as np

from tools.debug_association_pss_frequency import score_sensitivity


def test_equal_residuals_can_lose_likelihood_due_to_covariance_normalization():
    rows = score_sensitivity()
    assert len({r["rms_hz"] for r in rows}) == 1
    assert rows[1]["quadratic"] < rows[0]["quadratic"]
    assert rows[1]["nll"] > rows[0]["nll"] + 10
    for r in rows:
        assert np.isclose(r["nll"], 0.5 * (r["quadratic"] + r["logdet"] + 14 * np.log(2 * np.pi)))
