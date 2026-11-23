from importlib import import_module
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


BOOTSTRAP = runpy.run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/unified_short_bootstrap.py"))
Handoff = BOOTSTRAP["Handoff"]


def test_real_packet_handoff_runs_once_and_preserves_anchor_asset_pin():
    packet = {"source": {"probes": [{"candidates": [{"candidate_rank": 0}]}]}}
    scan = SimpleNamespace(acquire=object(), PINS={"cancellation-factors.so": "checked-anchor"})
    original = scan.acquire
    handoff = Handoff("session", "inventory", "actual-mixed-recipe", packet)
    with handoff.install(scan):
        with pytest.raises(ValueError, match="authenticated raw acquisition"):
            scan.acquire("session", "other inventory")
        assert handoff.calls == 0
        assert scan.PINS["cancellation-factors.so"] == "checked-anchor"
        assert scan.acquire("session", "inventory") is packet
        assert scan.PINS["cancellation-factors.so"] == "actual-mixed-recipe"
        with pytest.raises(ValueError, match="one handoff"):
            scan.acquire("session", "inventory")
    assert scan.acquire is original
    assert scan.PINS["cancellation-factors.so"] == "checked-anchor"


def test_empty_short_packet_has_original_withholding_contract(tmp_path):
    packet = {"source": {"probes": [{"candidates": []}]}}
    handoff = Handoff("session", "inventory", "actual-mixed-recipe", packet)
    scan = SimpleNamespace(acquire=None, PINS={"cancellation-factors.so": "checked-anchor"})
    args = SimpleNamespace(recording="recording", output=tmp_path / "new", archive="archive")

    def analyze(recording, output, assets, archive, offer):
        assert (recording, output, assets, archive, offer) == (args.recording, args.output, "assets", args.archive, "offer")
        assert scan.acquire("session", "inventory", {}, assets) is packet
        assert scan.PINS["cancellation-factors.so"] == "actual-mixed-recipe"
        return scan.solve(packet, scan.TleArchiveReader(archive), assets, offer)

    scan.analyze = analyze
    assert BOOTSTRAP["withhold"](scan, args, "offer", "assets", handoff, "no_active_curvature") == (
        {"status": "withheld", "reason": "no_active_curvature", "arms": {"c0": {"latlon": None}, "fitted_c": {"latlon": None}}},
        None, "stock",
    )
    assert args.output.is_dir()
    assert handoff.calls == 1


def test_one_selected_native_factor_cannot_take_zero_shortcut(tmp_path):
    native = {"source": {"probes": [{"candidates": []}, {"candidates": [{"candidate_rank": 0}]}]}}
    handoff = Handoff("session", "inventory", "actual-mixed-recipe", native)
    with pytest.raises(ValueError, match="ordinary numerical path"):
        BOOTSTRAP["withhold"](None, None, None, None, handoff, "no_active_curvature")
    assert handoff.calls == 0


def test_nonempty_graph_proof_for_another_packet_cannot_seal_the_result():
    native = {"source": {"probes": [{"candidates": [{"candidate_rank": 0}]}]}}
    handoff = Handoff("session", "inventory", "actual-mixed-recipe", native)
    with pytest.raises(ValueError, match="ordinary numerical path"):
        BOOTSTRAP["withhold"](None, None, None, None, handoff, "no_active_curvature",
                             graph_proof={"proven": True, "native_sha256": "sha256:other"})


def test_qualified_receiver_shim_is_scoped_and_fails_if_already_imported():
    name = "_unified_test_receiver_module"
    names = ("Native", "Factor", "_probe", "factor_candidate")
    symbols = {key: object() for key in names}
    with BOOTSTRAP["receiver_import"](name, symbols):
        assert all(getattr(import_module(name), key) is symbols[key] for key in names)
        with pytest.raises(ValueError, match="fresh native binding"):
            with BOOTSTRAP["receiver_import"](name, symbols):
                pytest.fail("replaced an active receiver")
    assert name not in sys.modules
