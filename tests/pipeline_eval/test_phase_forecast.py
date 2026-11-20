from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.qualification import phase_forecast_catalogue, phase_forecast_history
from tools.pipeline_eval.variants import phase_forecast

FIRST = b"1 67315U 26002L   26300.49854360  .00020640  00000-0  75560-3 0  9990"
SECOND = b"2 67315  42.9894  95.8956 0002076 230.4470 129.6199 15.27660566 46592"


def test_phase_is_an_advance_of_the_current_orbit():
    previous, current, velocity = (np.array(v) for v in ((0, 0, 0), (9, 2, 0), (3, 0, 0)))
    offset, transverse = phase_forecast.phase_delta(previous, velocity, current)
    assert offset == 3.0 and transverse == 2.0
    assert phase_forecast.physical_mean(previous, current, velocity, 8, 8) == 1.5
    assert phase_forecast.physical_mean(current, previous, velocity, 8, 8) == -1.5


def test_short_gaps_and_transverse_disagreement_shrink_to_zero():
    previous = np.zeros(3)
    velocity = np.array([3.0, 0.0, 0.0])
    assert phase_forecast.physical_mean(previous, np.array([9.0, 2.0, 0.0]), velocity, 8, 3) == 0.75
    assert phase_forecast.physical_mean(previous, np.array([9.0, 2.0, 0.0]), velocity, 8, 1) == 0.0
    assert phase_forecast.physical_mean(previous, np.array([9.0, 30.0, 0.0]), velocity, 8, 8) == 0.0


def test_future_history_and_in_interval_proxy_reject_before_access():
    sat = phase_forecast.as_satellite(FIRST, SECOND)
    epoch = phase_forecast.epoch_ns(sat)
    document = {
        "catalog_timestamp_ns": epoch + 3,
        "cutoff_utc_ns": epoch + 4,
        "anchor_utc_ns": epoch + 5,
    }
    assert phase_forecast.mean_forecast([sat], {}, document).tolist() == [0.0]
    bad_entry = {"collection_ns": epoch + 4, "path": Path("never-open"), "sha256": "unused"}
    with pytest.raises(ValueError, match="unauthorized"):
        phase_forecast_history.predecessors([sat], document, [bad_entry], {})
    with pytest.raises(ValueError, match="proxy element"):
        phase_forecast_catalogue.proxy(sat, sat, epoch - 60 * phase_forecast.SECOND)
