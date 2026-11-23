import importlib
from pathlib import Path
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def runner(monkeypatch):
    here = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(here))
    return importlib.import_module("full_short_run")


@pytest.mark.parametrize("mode", ["raw", "saved"])
@pytest.mark.parametrize("installed_graph", [False, True])
@pytest.mark.parametrize("row_reuse", [False, True])
def test_supplied_region_archive_and_receiver_reach_solver(runner, monkeypatch, tmp_path, mode, installed_graph, row_reuse):
    observed = {}
    class Receiver:
        def __init__(self, path, pin, *, full_coverage):
            observed["receiver"] = (path, pin, full_coverage)

        def detector(self):
            pass

    def observe(args, **options):
        observed["args"], observed["options"] = args, options
        args.output.mkdir()

    paths = {name: tmp_path / name for name in ("recording", "archive", "region", "output")}
    argv = [item for name, path in paths.items() for item in ("--" + name, str(path))]
    extra = ["--saved", "saved.json", "--saved-digest", "original"] if mode == "saved" else ["--short-binary", "short.so"]
    monkeypatch.setattr(runner, "MixedApertureDetector", Receiver)
    monkeypatch.setattr(runner, "run", observe)
    runner.main(argv + extra + (["--track-graph", "installed"] if installed_graph else [])
                + (["--reuse-cold-track-rows"] if row_reuse else []))
    args, options = observed["args"], observed["options"]
    assert all(getattr(args, name) == path for name, path in paths.items())
    assert args.verify_images and args.optimized_full_catalogue and options["early_regional"]
    assert options["track_config"] is (None if installed_graph else runner.graph_config)
    assert options["reuse_cold_rows"] is row_reuse
    sealed = json.loads((args.output / "full-short-recipe.json").read_bytes())
    assert sealed["graph"] == ("installed" if installed_graph else runner.GRAPH)
    assert sealed.get("reuse_cold_track_rows", False) is row_reuse
    if mode == "raw":
        assert observed["receiver"] == (Path("short.so"), runner.SHORT_SHA, True)
        assert options["raw_context"] and options["saved_receiver"] is None
    else:
        assert "receiver" not in observed
        assert options["raw_context"] is None and options["saved_receiver"] == runner.RECIPE_SHA


def test_rejects_altered_schedule_before_solving(runner, monkeypatch):
    original = runner.recipe()
    monkeypatch.setattr(runner, "recipe", lambda: {**original, "aperture_samples": [200000, 100000]})
    with pytest.raises(ValueError, match="schedule changed"):
        runner.checked_recipe()


def test_empty_input_keeps_installed_withhold_without_starting_region_search(runner, monkeypatch, tmp_path):
    from tools import algo08_scan

    publication = importlib.import_module("joint_publication")
    monkeypatch.setattr(publication, "machine", lambda: {"cpu": [2]})
    native = {"source": {"probes": []}}

    def analyze():
        decision, packet, _ = algo08_scan.solve(native, None, None, None)
        assert packet is None
        return {"decision": decision["status"]}

    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    monkeypatch.setattr(publication, "configuration", lambda: (
        SimpleNamespace(run=lambda args, spec: algo08_scan.analyze()), {}))
    args = SimpleNamespace(output=tmp_path / "empty", recording=None, archive=None, region=None,
                           saved=None, saved_digest=None, verify_images=False, optimized_full_catalogue=True)
    publication.run(args, early_regional=True)
    report = json.loads((args.output / "joint-research-receipt.json").read_bytes())
    assert report["route"] == "withheld_empty_receiver"
    assert report["receipt"]["decision"] == "withheld" and report["early_regional"] == []
