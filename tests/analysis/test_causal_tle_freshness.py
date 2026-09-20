"""Fresh collection must not override a newer, causally available element epoch."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest


def test_newest_epoch_respects_both_causal_times(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from audit_causal_tle_freshness import newest_causal

    rows = [
        dict(epoch_utc_ns=epoch, collected_utc_ns=collected, digest=str(i))
        for i, (epoch, collected) in enumerate([(80, 85), (60, 99), (95, 105), (110, 90)])
    ]
    assert newest_causal(rows, 100) is rows[0]
    assert newest_causal(rows, 106) is rows[2]
    with pytest.raises(ValueError, match="no causal"):
        newest_causal(rows, 70)


def test_offline_nearest_epoch_is_explicitly_different_from_causal(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from audit_causal_tle_freshness import nearest_offline, newest_causal

    rows = [
        dict(epoch_utc_ns=80, collected_utc_ns=90, digest="a"),
        dict(epoch_utc_ns=101, collected_utc_ns=110, digest="b"),
        dict(epoch_utc_ns=130, collected_utc_ns=150, digest="c"),
    ]
    assert nearest_offline(rows, 100) is rows[1]
    assert nearest_offline(rows, 100, "preceding") is rows[0]
    assert nearest_offline(rows, 100, "succeeding") is rows[1]
    with pytest.raises(ValueError, match="no archived"):
        nearest_offline(rows, 150, "succeeding")
    with pytest.raises(ValueError, match="unknown epoch side"):
        nearest_offline(rows, 100, "typo")
    assert newest_causal(rows, 100) is rows[0]
    with pytest.raises(ValueError, match="no archived"):
        nearest_offline([], 100)


@pytest.mark.parametrize("epoch, collected", [(110, 90), (90, 110), (50, 60)])
def test_replay_rejects_future_or_non_newer_elements(tmp_path, monkeypatch, epoch, collected):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    import replay_fresher_causal_tles as module

    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "norad": 12345,
                        "strictly_newer_epoch": True,
                        "nominal_epoch_utc_ns": 80,
                        "measurement_utc_ns": 100,
                        "selected": {"epoch_utc_ns": epoch, "collected_utc_ns": collected},
                    }
                ]
            }
        )
    )
    states = tmp_path / "states.npz"
    np.savez(states, segment=[0, 0], norad=[12345, 12345])
    parent, info = tmp_path / "parent.json", tmp_path / "info.json"
    parent.write_text("{}")
    info.write_text("{}")
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--audit",
            str(audit),
            "--states",
            str(states),
            "--parent",
            str(parent),
            "--information",
            str(info),
            "--evidence",
            str(tmp_path),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(ValueError, match="non-causal or non-newer"):
        module.main()
    assert not output.exists()
