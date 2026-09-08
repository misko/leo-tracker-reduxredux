"""Pure tests of benchmark partitioning and threshold freeze, no corpus required."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def tool():
    path = Path(__file__).parents[2] / "tools" / "evaluate_arm_presence.py"
    spec = importlib.util.spec_from_file_location("evaluate_arm_presence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scan_splits_disjoint_and_rate_balanced():
    entries = tool().SESSIONS
    assert len({session for _, session, _ in entries}) == 4
    for split in ("develop", "heldout"):
        assert sorted(rate for selected, _, rate in entries if selected == split) == [
            2_500_000,
            5_000_000,
        ]


def test_thresholds_use_development_controls_and_dual_receiver_maximum(tmp_path):
    module = tool()
    rows = [
        {
            "rate_hz": rate,
            "receivers": [{"scouts": {"lag_full120": {"score": score}}} for score in (1.0, 2.0)],
        }
        for rate in (2_500_000, 5_000_000)
    ]
    (tmp_path / "develop-controls.jsonl").write_text("\n".join(map(json.dumps, rows)))
    # Heldout scores, even when present, must not alter a development threshold.
    (tmp_path / "heldout-controls.jsonl").write_text("not read")
    module.thresholds(tmp_path)
    result = json.loads((tmp_path / "thresholds.json").read_text())
    assert 2 < result["thresholds"]["2500000"]["lag_full120"] < 2.000001
    with pytest.raises(FileExistsError):
        module.thresholds(tmp_path)


def test_artifacts_are_not_silently_overwritten(tmp_path):
    path = tmp_path / "artifact.json"
    module = tool()
    module.write_new(path, {"sealed": True})
    with pytest.raises(FileExistsError):
        module.write_new(path, {"sealed": False})
    assert json.loads(path.read_text()) == {"sealed": True}


@pytest.mark.parametrize("edge,expected", [("lower", -115_195_312.5), ("upper", 115_195_312.5)])
def test_pss_uses_reviewed_half_bin_projection(edge, expected):
    module = tool()
    for channel in range(1, 5):
        offset = module.starlink_edge_if_center_frequency_hz(channel, edge) - (
            module.starlink_pss_channel_reference_hz(channel, edge)
        )
        assert offset == expected


def test_reference_results_cannot_seed_causal_cache(monkeypatch, tmp_path):
    module = tool()
    events = []
    from leo.analysis.research.arm_presence import PresenceCandidate

    positive = PresenceCandidate(120, 0.1, 0.0, 0.0, 0.1, 0.2)

    def read_visit(index):
        span = SimpleNamespace(
            target=SimpleNamespace(channel=1, edge="lower"),
            actual_if_center_hz=959_687_500,
            target_index=0,
            valid_device_sample_counter=index * 1_000_000,
        )
        return SimpleNamespace(
            span=span, complex_samples=lambda: np.zeros((300_000, 2), np.complex64)
        )

    source = SimpleNamespace(
        session_id="synthetic",
        input_manifest_sha256="digest",
        sample_rate_hz=2_500_000,
        read_visit=read_visit,
    )
    monkeypatch.setattr(
        module, "PersistentHopIqStore", SimpleNamespace(open_read_only=lambda root: None)
    )
    monkeypatch.setattr(
        module,
        "PersistentHopAnalysisInputStore",
        lambda store: SimpleNamespace(source=lambda session: source),
    )
    monkeypatch.setattr(module, "scout_windows", lambda *args: {})

    def cold(*args, **kwargs):
        events.append("cold")
        return ()

    def reference(*args):
        events.append("reference")
        return [(positive,)] * 6, [{"cpu_ms": 0.0, "wall_ms": 0.0}] * 6

    def forbidden_cache(*args, **kwargs):
        pytest.fail("reference-positive evidence leaked into cache")

    monkeypatch.setattr(module, "fresh_glrt", cold)
    monkeypatch.setattr(module, "_reference_windows", reference)
    monkeypatch.setattr(module, "cached_glrt", forbidden_cache)
    protocol = {
        "sessions": [
            {
                "split": "develop",
                "session_id": "synthetic",
                "input_manifest_sha256": "digest",
                "visit_indexes": [0, 8],
            }
        ],
        "reference_windows_ms": [0, 20, 40, 60, 80, 100],
    }
    module.run_archive(tmp_path, tmp_path, "develop", protocol, {})
    assert events == ["cold", "reference"] * 4
