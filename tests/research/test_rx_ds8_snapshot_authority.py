import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.rx_ds8_snapshot_authority import LAG_NS, build_authority


class Store:
    def load(self, sid):
        return SimpleNamespace(
            input_manifest_sha256=f"input-{sid}",
            analysis_manifest_sha256=f"analysis-{sid}",
            timing=SimpleNamespace(first_sample_estimate_utc_ns=2_000_000_000_000),
        )


class Archive:
    def __init__(self, future=False):
        self.future = future
        self.cutoffs = []

    def select_latest_before(self, cutoff):
        self.cutoffs.append(cutoff)
        return SimpleNamespace(
            collected_utc_ns=cutoff + (1 if self.future else -1),
            digest="sha256:snapshot",
            provider="test",
        )

    def read(self, _snapshot):
        return "verified"


def fixture(tmp_path: Path):
    selected = []
    pose_dir = tmp_path / "pose"
    pose_dir.mkdir()
    for index in range(4):
        sid = f"s{index}"
        selected.append(
            {
                "session_id": sid,
                "input_manifest_sha256": f"input-{sid}",
                "analysis_manifest_sha256": f"analysis-{sid}",
                "pose_binding_digest": f"pose-{sid}",
            }
        )
        (pose_dir / f"{sid}.json").write_text(
            json.dumps(
                {
                    "binding_digest": f"pose-{sid}",
                    "pose_authority": {"latitude_deg": 1.0, "longitude_deg": 2.0},
                }
            )
        )
    return {"selected": selected}, pose_dir


def test_builds_exact_strictly_causal_authority(tmp_path):
    readiness, poses = fixture(tmp_path)
    archive = Archive()
    authority, receipt = build_authority(readiness, poses, Store(), archive)
    assert set(authority["sessions"]) == {"s0", "s1", "s2", "s3"}
    assert archive.cutoffs == [2_000_000_000_000 - LAG_NS] * 4
    assert all(row["strictly_before_cutoff"] for row in receipt)
    assert authority["sessions"]["s0"]["site"] == {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
    }


def test_rejects_noncausal_archive_result(tmp_path):
    readiness, poses = fixture(tmp_path)
    with pytest.raises(ValueError, match="not strictly causal"):
        build_authority(readiness, poses, Store(), Archive(future=True))
