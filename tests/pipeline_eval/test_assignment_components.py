from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from assignment_components import assignments, census, components


def test_phase_alternatives_and_fitted_calibration_connect_distinct_receivers():
    left = "SCAN-RX1-CH2-T002-RF10600000000"
    right = "SCAN-RX2-CH6-T001-RF12100000000"
    first = [[left, 1, 100, 0], [right, 2, 200, -1]]
    separate = census([first])["groups"]
    assert separate["receiver_band_offsets_free"]["sizes"] == [1, 1]
    assert separate["receiver_band_offsets_and_calibration_free"]["sizes"] == [2]
    second = [[left, 2, 200, 0], [right, 2, 200, -1]]
    linked = census([first, second])
    assert linked["changed_tracks"] == 1
    assert linked["groups"]["receiver_parameters_fixed"]["tracks_in_groups_containing_changes"] == 2


def test_shared_band_offsets_and_no_calibration_at_reference_rf():
    tracks = ["SCAN-RX1-CH1-T001-RF11500000000", "SCAN-RX1-CH3-T002-RF11500000000",
              "SCAN-RX2-CH2-T001-RF11500000000"]
    sig = [[track, i, i, 0] for i, track in enumerate(tracks)]
    result = census([sig])["groups"]
    assert result["receiver_parameters_fixed"]["sizes"] == [1, 1, 1]
    assert result["receiver_band_offsets_and_calibration_free"]["sizes"] == [2, 1]
    with pytest.raises(ValueError):
        assignments(sig + sig[:1])
    with pytest.raises(ValueError):
        components([assignments(sig), assignments(sig[:1])], receiver_offsets=True, fitted_c=False)
