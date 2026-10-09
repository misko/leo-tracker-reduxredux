from types import SimpleNamespace

import pytest

from leo.cli import regional_position as cli
from leo.storage.regional_position_v3 import B7Store

DIGEST = "sha256:" + "a" * 64


def test_insufficient_input_publishes_hard60_map_and_repeated_run_reuses_them(
    tmp_path, monkeypatch
):
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
    store = B7Store(tmp_path)
    document = store.status("scan-1").manifest.document
    assert all(method.state == "insufficient" for method in document.methods)
    for name in ("V16",):
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
    assert config["run"]["levels_km"] == [40, 20, 10, 5]
    assert config["prior"]["radius_km"] == 250
    assert config["refinement"] == "off"
    assert set(config["scores"]) == {"V16"}
    assert "application/regional_position_runner.py" in config["source_digests"]
    assert config["scores"]["V16"]["relative_sigma_s"] == 2
    assert config["scores"]["V16"]["common_sigma_s"] == 3
    assert config["run"]["slope_half_width_hz_s"] == 60
    assert config["run"]["edge_priority"] == "nearest"
    assert config["run"]["recovery_policy"] == "failed-coarse-box-v1"
    assert "analysis/hard60_bounded_fit.py" in config["source_digests"]
    assert "application/hard60_recovery.py" in config["source_digests"]


def test_legacy_publication_cannot_satisfy_new_completion(tmp_path):
    from leo.storage.regional_position import RegionalPositionStore
    from tests.contracts.test_regional_position_products import document

    png = b"\x89PNG\r\n\x1a\nfixture"
    RegionalPositionStore(tmp_path, read_only=False).publish(document(), {"T1AT": png, "V16": png})
    assert not cli.regional_position_complete(tmp_path, "scan-1")
