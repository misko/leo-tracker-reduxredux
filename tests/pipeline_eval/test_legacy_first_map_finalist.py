import sys
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.legacy_first_map_acceleration import solver_ports
from reports.ALGO08.v3.legacy_first_map_finalist import options


def test_first_use_options_bind_only_the_new_artifacts(tmp_path):
    original = ["entry", "--legacy-first-map-history", "old.so",
                "--legacy-first-map-history-sha256", "old-pin", "--history-risk-route"]
    prepared = options(original, tmp_path / "history.so", "new-pin", tmp_path / "exact.json", "config-pin")
    assert prepared[:6] == ["entry", "--legacy-first-map-history", str(tmp_path / "history.so"),
                            "--legacy-first-map-history-sha256", "new-pin", "--history-risk-route"]
    assert prepared[6:] == ["--legacy-first-map-fast", str(tmp_path / "exact.json"),
                            "--legacy-first-map-fast-sha256", "config-pin"]
    assert original[2] == "old.so"
    with pytest.raises(ValueError, match="no waveform custody"):
        options([*original, "--legacy-first-map-plan"], "new", "hash", "config", "config-pin")


def test_receiver_side_withhold_never_enters_scientific_ports(monkeypatch):
    def publication():
        raise AssertionError("The early receiver path never calls the fit")

    scope = SimpleNamespace(publish_active=publication)
    monkeypatch.setitem(sys.modules, "exact_named_raw", scope)
    audit = {}
    with solver_ports({}, audit):
        assert scope.publish_active is not publication
        assert audit == {}
    assert scope.publish_active is publication
