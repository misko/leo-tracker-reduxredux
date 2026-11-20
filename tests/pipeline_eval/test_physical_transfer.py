import json

import numpy as np
import pytest

from tools.pipeline_eval.qualification.physical_transfer import cohort, packet
from tools.pipeline_eval.qualification.physical_transfer_solver import profile_cfo, solve


def test_cohort_uses_first_capture_per_distinct_group():
    captures = [dict(site_group=f"site-{i}", pair=f"first-{i}") for i in range(1, 7)] + [
        dict(site_group="site-5", pair="repeat")
    ]
    assert cohort(captures) == [(f"site-{i}", f"first-{i}") for i in range(3, 7)]


def test_global_packet_excludes_tile_and_any_site_or_satellite_labels():
    observation = dict(
        anchor_utc_ns=10,
        cutoff_utc_ns=10,
        catalog_timestamp_ns=9,
        duration_s=30,
        tracks=[dict(channel=3, receiver=1, rf_hz=11.325e9, times=[0, 1], values=[500.0, 200.0])],
    )
    payload = json.loads(packet("alias", observation, "tle", "digest", None))
    assert set(payload) == {"id", "observation", "catalogue", "solver_sha256"}
    observation["tracks"][0]["norad"] = 42
    with pytest.raises(ValueError, match="undeclared fields"):
        packet("alias", observation, "tle", "digest", None)


def test_offset_cancels_both_calibration_arms_and_does_not_refit_on_holdout():
    projected = np.arange(9) * 400.0
    observed = projected + 9650
    observed[6:] += 200
    initial = profile_cfo(observed, projected)
    shifted = profile_cfo(observed + 255_000, projected)
    assert initial == (0, 200**2)
    assert shifted == initial


def test_empty_prepared_input_withholds_without_a_site():
    result = solve(dict(tracks=[]), "")
    assert result["status"] == "withheld"
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    assert result["arms"]["c0"]["forced_latlon"] is None
