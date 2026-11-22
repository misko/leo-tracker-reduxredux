from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.presentation import localization_v3
from tools import algo08_position, algo08_scan
from tools.pipeline_eval.qualification import experimental_publication as launcher
from tools.pipeline_eval.qualification import freeze_publication as freezer
from tools.pipeline_eval.qualification.paired_publication import verify_sources
from tools.pipeline_eval.variants import algo08_posterior_handoff


@pytest.mark.parametrize("solver", ["screened-stock-finish", "screened-tiled-finish"])
def test_screened_launcher_uses_selected_salvage_and_original_inference(tmp_path, monkeypatch, solver):
    from leo.analysis.localization_v3 import conservative_recovery
    from tools.pipeline_eval.variants import v5_core, v5_screen_winner

    output = tmp_path / "output"
    output.mkdir()
    region = tmp_path / "region.json"
    region.write_text(json.dumps(dict(center=[10., 69.], width_km=25.)))
    detector = tmp_path / "detector.so"
    detector.write_bytes(b"reviewed")
    spec = dict(detector=str(detector), detector_sha256=sha256(detector.read_bytes()).hexdigest(),
                solver=solver)
    args = SimpleNamespace(recording=tmp_path / "capture", bulk_root=output, archive=tmp_path / "tle", region=region)
    old_salvage, old_infer, old_selection = conservative_recovery.salvage, v5_core.infer, v5_core.initial_selection

    def screen(scan, ranked, metrics):
        metrics["winning_rank"] = 1
        return ranked[1], len(ranked)

    def analyze(*unused):
        assert (conservative_recovery.salvage is old_salvage) == (solver == "screened-stock-finish")
        assert v5_core.infer is old_infer
        with monkeypatch.context() as patches:
            patches.setattr(v5_core, "ranked_initial_nodes", lambda _: [3, 4, 5])
            assert v5_core.initial_selection(None) == (4, 3)
        return {"decision": "complete"}

    monkeypatch.setattr(v5_screen_winner, "screen_nodes", screen)
    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    assert launcher.run(args, spec)["screened_nomination"] == {"winning_rank": 1}
    assert v5_core.initial_selection is old_selection and conservative_recovery.salvage is old_salvage


@pytest.mark.parametrize("solver", ["collapsed-signed", "screened-stock-finish", "screened-tiled-finish"])
def test_freezer_only_copies_explicit_reviewed_handoff(tmp_path, solver):
    checkout = Path(__file__).resolve().parents[2]
    release = tmp_path / "release"
    (release / "tools").mkdir(parents=True)
    detector = tmp_path / "receiver.so"
    detector.write_bytes(b"detector fixture")
    library = tmp_path / "test.so"
    library.write_bytes(b"pinned posterior factor fixture")
    digest = sha256(library.read_bytes()).hexdigest()
    detector_hash = sha256(detector.read_bytes()).hexdigest()
    bundle = tmp_path / "bundle"

    def freeze(root, solver, **options):
        return freezer.freeze(checkout, root, detector, detector_hash, solver, "stock", release, **options)

    stock = tmp_path / "default"
    assert "posterior_grid_handoff" not in freeze(stock, solver)
    assert not (stock / launcher.POSTERIOR_GRID_LIBRARY).exists()
    for suffix in ("py", "h"):
        assert not (stock / freezer.VARIANTS / f"algo08_posterior_handoff.{suffix}").exists()
    with pytest.raises(ValueError, match="requires the collapsed-signed"):
        freeze(bundle, "stock", posterior_grid_handoff=(library, digest))
    with pytest.raises(ValueError, match="differs from its reviewed build"):
        freeze(bundle, solver, posterior_grid_handoff=(library, "0" * 64))
    assert not bundle.exists()
    spec = freeze(bundle, solver, posterior_grid_handoff=(library, digest))
    if solver in ("screened-stock-finish", "screened-tiled-finish"):
        modules = {Path(name).stem for name in spec["sources"]}
        assert {"algo08_stock_finish", "v5_screen_winner", "algo08_causal_table"} <= modules
        assert "algo08_collapsed_repair" not in modules
        for tile_module in ("algo08_salvage_statistics", "algo08_salvage_bound"):
            assert (tile_module in modules) == (solver == "screened-tiled-finish")
    binary = bundle / launcher.POSTERIOR_GRID_LIBRARY
    assert spec["posterior_grid_handoff"] == dict(library=str(binary), sha256=digest)
    assert binary.read_bytes() == library.read_bytes()
    for suffix in ("py", "h"):
        path = freezer.VARIANTS / f"algo08_posterior_handoff.{suffix}"
        assert spec["sources"][str(path)] == sha256((checkout / path).read_bytes()).hexdigest()
    verify_sources(bundle / freezer.LAUNCHER, spec["sources"])


@pytest.mark.parametrize("mode", ["disabled", "eligible", "no-predictions", "tampered"])
def test_launcher_scopes_verified_factor_to_grid_and_identifies_its_arithmetic(tmp_path, monkeypatch, mode):
    output, archive = tmp_path / "output", tmp_path / "archive"
    output.mkdir()
    offer = tmp_path / "offer.json"
    offer.write_text(json.dumps(dict(center=[-32., 115.], width_km=25.)))
    detector = tmp_path / "receiver.so"
    detector.write_bytes(b"detector fixture")
    library = tmp_path / "reference.so"
    reviewed = b"approved fixture"
    library.write_bytes(b"tampered fixture" if mode == "tampered" else reviewed)
    spec = dict(detector=str(detector), detector_sha256=sha256(detector.read_bytes()).hexdigest(),
                solver="collapsed-signed")
    if mode != "disabled":
        spec["posterior_grid_handoff"] = dict(library=str(library), sha256=sha256(reviewed).hexdigest())
    args = SimpleNamespace(recording=tmp_path / "opaque", bulk_root=output, archive=archive, region=offer)
    counts, checks = Counter(), {}

    @contextmanager
    def fake_binding(port, binary, in_grid):
        assert port is algo08_position and binary != library and binary.is_file()
        assert binary.read_bytes() == reviewed
        assert not in_grid()
        checks.update(in_grid=in_grid, library=binary)
        yield counts
        assert not in_grid()

    def sample():
        if mode != "disabled":
            assert checks["in_grid"]()
        if mode == "eligible":
            counts["factor_calls"] += 1
        return dict(nuisance_model="unchanged published marginal likelihood", complete=True)

    def analyze(recording, root, assets, causal_archive, region):
        assert recording == args.recording and root == output and causal_archive == archive
        assert region.center == (-32., 115.)
        assert (assets / "native").readlink() == launcher.RELEASE / "assets" / "native"
        if mode != "disabled":
            assert checks["library"].parent == assets and not checks["in_grid"]()
        grid = localization_v3.sample_position_grid()
        return dict(grid=grid, decision="complete")

    monkeypatch.setattr(algo08_posterior_handoff, "grid_handoff", fake_binding)
    monkeypatch.setattr(localization_v3, "sample_position_grid", sample)
    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    if mode == "tampered":
        with pytest.raises(ValueError, match="differs from its reviewed build"):
            launcher.run(args, spec)
        assert not checks and not list(output.iterdir())
        return
    result = launcher.run(args, spec)
    assert localization_v3.sample_position_grid is sample
    if mode == "eligible":
        assert result["posterior_grid_handoff"]["factor_calls"] == 1
        assert "research permuted native posterior factor" in result["grid"]["nuisance_model"]
    else:
        assert result["grid"]["nuisance_model"] == "unchanged published marginal likelihood"
        assert not result.get("posterior_grid_handoff", {}).get("factor_calls")
    assert ("posterior_grid_handoff" in result) == (mode != "disabled")
