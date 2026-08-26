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
