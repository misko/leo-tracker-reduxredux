from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tools import experiment_retrospective_satellite_nuisance as tool

ROOT = Path(__file__).parents[2]
PROTOCOL = ROOT / "config/analysis/retrospective-satellite-nuisance-protocol-v1.json"


def test_frozen_measurement_bundles_load_with_expected_mixed_estimators() -> None:
    protocol = tool.load_protocol(PROTOCOL)
    tracks = tool.load_bound_tracks(protocol)

    assert len(tracks) == 5
    assert sum(item.primary for item in tracks) == 4
    assert [item.track.path_ids.__len__() for item in tracks] == [4, 3, 4, 4, 1]
    assert tracks[-1].bundle_id == "long-direct-glrt"
    assert tracks[-1].track.time_s.size >= 500
    assert all(np.isfinite(item.track.fit_cfo_hz).all() for item in tracks)
    reduction = protocol["measurement_reduction"]
    diagnostic = next(item for item in tracks if not item.primary)
    support_pass, support = tool._support_disposition(diagnostic, reduction)
    assert support_pass is False
    assert any(int(item["evaluation_bin_count"]) < 20 for item in support)


def test_protocol_load_fails_on_measurement_digest_drift(tmp_path: Path) -> None:
    document = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    document["measurement_inputs"]["long_150802_ledger"]["sha256"] = "sha256:" + "0" * 64
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="digest drifted"):
        tool.load_protocol(path)


def test_path_radio_parser_fails_closed() -> None:
    assert tool._path_radio("stream-0/radio_pluto_5d4d/RX1") == "radio_pluto_5d4d"
    with pytest.raises(ValueError, match="malformed"):
        tool._path_radio("stream-0/RX1")


def test_floating_grid_endpoint_is_not_mistaken_for_interior() -> None:
    assert not tool._grid_value_is_interior(0.2499999999999999, -0.25, 0.25, 0.025)
    assert tool._grid_value_is_interior(0.225, -0.25, 0.25, 0.025)
    assert tool._winner_nuisance_is_interior({"radio_rate_departures_hz_s": [149.0, -149.0]}, 150.0)
    assert not tool._winner_nuisance_is_interior(
        {"radio_rate_departures_hz_s": [150.0, 1.0]}, 150.0
    )
