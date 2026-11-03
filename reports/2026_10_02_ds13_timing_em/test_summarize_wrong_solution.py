from types import SimpleNamespace

import numpy as np
from summarize_wrong_solution import residual_channels


def test_residual_summary_uses_winner_and_confidence_and_reports_empty_bins():
    data = SimpleNamespace(times=np.arange(4), measured=np.array([10., 20., 30., 40.]),
                           receiver=np.array([0, 0, 1, 1]), channel=np.array([1, 2, 1, 2]))
    predicted = np.array([[0., 0.], [0., 0.], [0., 25.], [0., 0.]])
    posterior = np.array([[.9, .0], [.7, .0], [.0, .9], [.0, .0]])
    result = residual_channels(data, predicted, posterior)
    assert [row["mean_hz"] for row in result] == [10., None, 5., None]
    assert [row["rows"] for row in result] == [1, 0, 1, 0]
