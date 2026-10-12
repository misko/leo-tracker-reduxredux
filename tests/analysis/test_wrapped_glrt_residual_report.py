import numpy as np

from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from tools.report_wrapped_glrt_residuals import summarize


def test_residual_bin_support_uses_signal_mass_instead_of_counting_peak_alternatives():
    data = FrequencyEvidence(
        ids=tuple(map(str, range(6))),
        frequency_hz=np.zeros((6, 2)),
        candidate_weight=np.tile([0.6, 0.4], (6, 1)),
        signal_probability=np.ones(6),
        group=np.zeros(6, int),
        time_s=np.arange(6.0),
    )
    residual = np.tile([10.0, 20.0], (6, 1))[:, :, None]
    mass = np.tile([0.6, 0.4], (6, 1))[:, :, None]
    rows = summarize(data, np.full(6, 11e9), residual, mass, [30])
    assert rows[0]["strong_signal_mass"] == 6
    assert len(rows[0]["temporal_bins"]) == 1
    assert rows[0]["temporal_bins"][0]["mass"] == 6
    assert rows[0]["temporal_bins"][0]["median_hz"] == 10
    assert summarize(data, np.full(6, 11e9), residual, mass / 2, [30])[0]["temporal_bins"] == []
