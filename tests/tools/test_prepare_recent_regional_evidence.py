from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _subject():
    path = Path(__file__).parents[2] / "tools/research/prepare_recent_regional_evidence.py"
    spec = importlib.util.spec_from_file_location("prepare_recent_regional_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Archive:
    snapshot = SimpleNamespace(digest="sha256:catalogue", collected_utc_ns=100)

    def list_snapshots(self):
        return (self.snapshot,)

    def read(self, snapshot):
        assert snapshot is self.snapshot
        return "causal tle\n"


def test_prepare_preserves_rf_authority_and_cross_receiver_pair_ids(tmp_path):
    subject = _subject()
    shard = {
        "session": {"session_id": "scan", "capture_start_utc_ns": 1_000_000_000},
        "catalogue_snapshot": {"digest": "sha256:catalogue", "collected_utc_ns": 100},
        "tracks": [
            {
                "tracklet_id": "track-rx1",
                "lane": {"channel": 2, "receiver_id": 1, "actual_rf_hz": 11_210_000_000},
                "observations": [
                    {
                        "observation_id": "observation",
                        "source_group_id": "visit-authority",
                        "support_center_utc_ns": 2_000_000_000,
                        "measured_cfo_hz": 125.0,
                    }
                ],
            }
        ],
    }
    shard_path = tmp_path / "scan.json"
    shard_path.write_text(json.dumps(shard))
    output = tmp_path / "evidence"
    inventory = subject.prepare((shard_path,), output, _Archive())
    document = json.loads((output / "evidence/scan.json").read_text())
    assert inventory["known_position_used"] is False
    assert inventory["prior_matched_norads_used"] is False
    assert document["inventory"]["fixed_candidates"] == {}
    assert document["series"] == [
        {
            "actual_rf_hz": 11_210_000_000,
            "candidate_ids": ["observation"],
            "channel": 2,
            "paired_visit_ids": ["visit-authority"],
            "receiver_id": 1,
            "t_s": [1.0],
            "tracklet_id": "track-rx1",
            "y_hz": [125.0],
        }
    ]


def test_prepare_rejects_missing_causal_snapshot(tmp_path):
    subject = _subject()
    shard_path = tmp_path / "scan.json"
    shard_path.write_text(
        json.dumps(
            {
                "session": {"session_id": "scan", "capture_start_utc_ns": 1},
                "catalogue_snapshot": {"digest": "other", "collected_utc_ns": 100},
                "tracks": [],
            }
        )
    )
    try:
        subject.prepare((shard_path,), tmp_path / "output", _Archive())
    except ValueError as error:
        assert "causal TLE" in str(error)
    else:
        raise AssertionError("missing causal snapshot was accepted")
