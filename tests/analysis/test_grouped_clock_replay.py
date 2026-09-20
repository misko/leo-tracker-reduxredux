"""Recording grouping must not accidentally reuse the sample-rate groups."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.parametrize("grouping, key", [("sample-rate", "rate"), ("recording", "session")])
def test_grouping_and_conditional_provenance(tmp_path, monkeypatch, grouping, key):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    import replay_sample_rate_clocks as module

    states = tmp_path / "states.npz"
    rate, session = np.array([10, 15, 10, 15]), np.array([0, 0, 1, 1])
    np.savez(
        states,
        **{
            "p0.0": np.zeros((4, 3)),
            "v0.0": np.zeros((4, 3)),
            "segment": np.arange(4),
            "rate": rate,
            "session": session,
        },
    )
    inference = tmp_path / "inference.json"
    inference.write_text(
        json.dumps(
            {
                "cohorts": {
                    "current_fov_selected": {
                        "region": dict(
                            latitude_deg=40, longitude_deg=-100, width_km=5000, height_km=5000
                        ),
                        "initial": [0, 0],
                    }
                },
                "identity_provenance": {
                    "current_fov_selected": "known-site conditional identities"
                },
            }
        )
    )
    info = tmp_path / "information.json"
    info.write_text(
        json.dumps(
            {
                "tracks": [
                    dict(segment=i, training_rms_hz=50 if i < 2 else 500, span_s=20)
                    for i in range(4)
                ]
            }
        )
    )
    calls = []

    def capture_fit(*args, **kwargs):
        calls.append(kwargs)
        return dict(latitude_deg=0, longitude_deg=0, clock_offsets_s=[])

    monkeypatch.setattr(module, "fit", capture_fit)
    output = tmp_path / "out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--states",
            str(states),
            "--inference",
            str(inference),
            "--information",
            str(info),
            "--output",
            str(output),
            "--grouping",
            grouping,
        ],
    )
    module.main()
    expected = rate if key == "rate" else session
    assert len(calls) == 4
    assert calls[0]["clock_groups"] is None
    assert calls[2]["clock_groups"] is None
    for index in [1, 3]:
        np.testing.assert_array_equal(calls[index]["clock_groups"], expected)
    np.testing.assert_array_equal(calls[3]["subset"], [True, True, False, False])
    result = json.loads(output.read_text())
    assert result["identity_provenance"] == "known-site conditional identities"
    assert result["evaluation_location_used"] is False
    assert [r["grouping"] for r in result["models"]] == ["shared", grouping] * 2
