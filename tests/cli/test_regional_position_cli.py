from types import SimpleNamespace

import pytest

from leo.cli import regional_position as cli
from leo.storage.regional_position import RegionalPositionStore

DIGEST = "sha256:" + "a" * 64


def test_insufficient_input_publishes_both_maps_and_repeated_run_reuses_them(tmp_path, monkeypatch):
    calls = []

    class Reader:
        def __init__(self, root):
            pass

        def load(self, session):
            return SimpleNamespace(input_manifest_sha256=DIGEST, analysis_manifest_sha256=DIGEST)

        def close(self):
            calls.append("close")

    def prepare(source):
        calls.append("prepare")
        raise cli.PositionInputUnavailable("no qualified UTC")

    monkeypatch.setattr(cli, "ScannerTrackingInputStore", Reader)
    monkeypatch.setattr(cli, "prepare_position_windows", prepare)
    first = cli.run_regional_position_analysis(tmp_path, tmp_path, "scan-1")
    assert first["state"] == "complete"
    store = RegionalPositionStore(tmp_path)
    document = store.status("scan-1").manifest.document
    assert all(method.state == "insufficient" for method in document.methods)
    for name in ("T1AT", "V16"):
        assert store.artifact("scan-1", name).startswith(b"\x89PNG\r\n\x1a\n")
    assert cli.regional_position_complete(
        tmp_path, "scan-1", expected_input=DIGEST, expected_analysis=DIGEST
    )
    assert not cli.regional_position_complete(
        tmp_path, "scan-1", expected_input="sha256:" + "b" * 64
    )
    assert cli.run_regional_position_analysis(tmp_path, tmp_path, "scan-1") == first
    assert calls == ["close", "prepare", "close"]


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), 1801])
def test_invalid_slice_budget_rejected_before_loading(seconds, tmp_path):
    with pytest.raises(ValueError, match="budget"):
        cli.run_regional_position_analysis(tmp_path, tmp_path, "scan-1", maximum_seconds=seconds)


def test_configuration_freezes_models_prior_and_full_search_budget():
    config = cli.configuration()
    assert config["run"]["point_budget"] == 400
    assert config["run"]["levels_km"] == [100, 50, 25, 12.5]
    assert config["prior"]["radius_km"] == 250
    assert config["refinement"] == "off"
    assert set(config["scores"]) == {"T1AT", "V16"}
    assert "application/regional_position_runner.py" in config["source_digests"]
