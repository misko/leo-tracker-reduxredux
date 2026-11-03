import copy

import numpy as np
import pytest
from test_rx_presence_geometry import _source

from tools import rx_presence_geometry as presence


def _prepare(source):
    return presence.prepare_lanes(
        {"schema": "rx-geometry-dataset/v1", "lanes": [source]},
        np.zeros(8),
        np.ones(8),
    )


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda source: source["components"].reverse(), "exactly one other"),
        (
            lambda source: source["components"].insert(
                0, {"kind": "other", "log_prior": None}
            ),
            "exactly one other",
        ),
        (
            lambda source: source["windows"][0]["predictions"].pop(),
            "cardinality mismatch",
        ),
        (
            lambda source: source["windows"][1].update(
                source_window_id=source["windows"][0]["source_window_id"]
            ),
            "must be unique",
        ),
        (
            lambda source: source["windows"][1].update(
                prediction_utc_ns=source["windows"][0]["prediction_utc_ns"]
            ),
            "strictly increasing",
        ),
        (
            lambda source: source["windows"].reverse(),
            "strictly increasing",
        ),
    ],
)
def test_prepare_rejects_malformed_component_and_window_structure(mutate, match) -> None:
    source = _source()
    mutate(source)
    with pytest.raises(ValueError, match=match):
        _prepare(source)


def test_prepare_rejects_interleaved_roles_even_with_chronological_times() -> None:
    source = _source()
    extra = copy.deepcopy(source["windows"][0])
    extra["prediction_utc_ns"] = 3_000_000_000
    extra["source_window_id"] = "late-reception"
    source["windows"].append(extra)
    with pytest.raises(ValueError, match="must precede"):
        _prepare(source)


def test_selection_exports_denominator_and_checks_real_null_density() -> None:
    lanes = _prepare(_source())
    presence.signal_arrays(lanes, 500.0)
    selection = presence.select_state(
        lanes,
        np.zeros(3),
        np.array([1.2, 0.8]),
        np.zeros(8),
        np.ones(8),
    )
    null = next(row for row in selection["grid"] if row["occupancy"] == 0.0)
    assert selection["calibration_reception_windows"] == 1
    assert null["calibration_log_score"] == pytest.approx(
        selection["analytical_absent_log_score"], abs=1e-12
    )
