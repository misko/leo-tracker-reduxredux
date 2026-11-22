"""The frozen Graph library is optional, private, and checked before use."""

from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis import graph_tracklets
from leo.analysis.localization_v3 import tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from tools import algo08_scan
from tools.pipeline_eval.qualification import experimental_publication as launcher
from tools.pipeline_eval.qualification import freeze_publication as freezer
from tools.pipeline_eval.qualification.paired_publication import verify_sources
from tools.pipeline_eval.variants.experimental import graph_path


pytestmark = pytest.mark.skipif(platform.machine() != "x86_64", reason="x86-64 Graph library")


def pin(path):
    return path, sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp("native-graph") / "graph.so"
    graph_path.build(path)
    return path


@pytest.fixture(scope="module")
def incompatible(tmp_path_factory):
    path = tmp_path_factory.mktemp("incompatible-graph") / "graph.so"
    subprocess.run(
        ["cc", "-shared", "-fPIC", "-xc", "-o", str(path), "-"],
        input="unsigned leo_graph_path_abi(void) { return 2; }\n"
              "void leo_graph_path_v1(void) {}\n",
        text=True, check=True,
    )
    return path


@pytest.fixture
def freeze(tmp_path):
    release = tmp_path / "release"
    (release / "tools").mkdir(parents=True)
    checkout = Path(freezer.__file__).resolve().parents[3]
    detector = tmp_path / "receiver.so"
    detector.write_bytes(b"pinned detector")

    def bundle(name, **options):
        return freezer.freeze(checkout, tmp_path / name, *pin(detector),
                              "stock", "stock", release, **options)

    return bundle


def test_freezer_pins_graph_kernel_and_adapter_only_when_enabled(freeze, library, incompatible, tmp_path):
    stock = freeze("stock")
    assert "graph_path" not in stock
    for source in (*launcher.GRAPH_PATH_SOURCES, launcher.GRAPH_PATH_LIBRARY):
        assert not (tmp_path / "stock" / source).exists()
    with pytest.raises(ValueError, match="differs from its reviewed build"):
        freeze("bundle", graph_path=(library, "0" * 64))
    with pytest.raises(ValueError, match="Unsupported native Graph path ABI"):
        freeze("bundle", graph_path=pin(incompatible))
    bundle = tmp_path / "bundle"
    assert not bundle.exists()
    spec = freeze("bundle", graph_path=pin(library))
    assert spec["graph_path"] == dict(library=str(bundle / launcher.GRAPH_PATH_LIBRARY), sha256=pin(library)[1])
    assert "graph_alias" not in spec
    assert not (bundle / freezer.VARIANTS / "experimental/graph_alias.py").exists()
    launcher_path = bundle / freezer.LAUNCHER
    verify_sources(launcher_path, spec["sources"])
    for source in (*launcher.GRAPH_PATH_SOURCES, launcher.GRAPH_PATH_LIBRARY):
        assert spec["sources"][str(source)] == pin(bundle / source)[1]
    (bundle / launcher.GRAPH_PATH_SOURCES[0]).write_text("changed")
    with pytest.raises(ValueError, match="Candidate source changed"):
        verify_sources(launcher_path, spec["sources"])


@pytest.fixture
def args(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    offer = tmp_path / "offer.json"
    offer.write_text(json.dumps(dict(center=[-32., 115.], width_km=25.)))
    return SimpleNamespace(bulk_root=output, recording=tmp_path / "opaque",
                           archive=tmp_path / "archive", region=offer)


@pytest.mark.parametrize("enabled", [False, True])
def test_launcher_uses_private_graph_library_and_restores_graph_port(
    freeze, library, args, monkeypatch, enabled,
):
    spec = freeze("bundle", **({"graph_path": pin(library)} if enabled else {}))
    t = np.arange(125) * .5
    y = 112000. - 500. * t + 3. * t**2
    config = TrackConfig()
    fit_lane, best_path = tracks.fit_lane, graph_tracklets._best_path
    stock = fit_lane(t, y, config)
    seen = []

    def analyze(_recording, _root, assets, _archive, _region):
        private = assets / launcher.GRAPH_PATH_LIBRARY
        assert private.exists() == enabled
        assert (tracks.fit_lane is not fit_lane) == enabled
        if enabled:
            assert private != Path(spec["graph_path"]["library"])
            assert private.read_bytes() == library.read_bytes()
            seen.append(private)
        result = tracks.fit_lane(t, y, config)
        for key in ("assignment", "alias_lifts"):
            np.testing.assert_array_equal(result[key], stock[key])
        for a, b in zip(result["tracks"][0]["pieces"], stock["tracks"][0]["pieces"], strict=True):
            assert a["coefficients_hz"].tobytes() == b["coefficients_hz"].tobytes()
        return {"decision": "complete"}

    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    result = launcher.run(args, spec)
    assert tracks.fit_lane is fit_lane and graph_tracklets._best_path is best_path
    if enabled:
        assert result["graph_path"]["native_paths"] > 0
        assert result["graph_path"].get("reference_paths", 0) == 0
        assert not seen[0].exists()
    else:
        assert "graph_path" not in result


@pytest.mark.parametrize("failure", ["digest", "source", "abi", "reference"])
def test_launcher_rejects_changed_or_incompatible_graph_pins_before_analysis(
    freeze, library, incompatible, args, monkeypatch, failure,
):
    spec = freeze("bundle", graph_path=pin(library))
    if failure == "digest":
        Path(spec["graph_path"]["library"]).write_bytes(b"unreviewed")
        expected = "library differs from its reviewed build"
    elif failure == "source":
        spec["sources"][str(launcher.GRAPH_PATH_SOURCES[0])] = "0" * 64
        expected = "Graph path source changed"
    elif failure == "abi":
        source, digest = pin(incompatible)
        spec["graph_path"] = dict(library=str(source), sha256=digest)
        spec["sources"][launcher.GRAPH_PATH_LIBRARY] = digest
        expected = "Unsupported native Graph path ABI"
    else:
        monkeypatch.setattr(graph_path, "REFERENCE_SHA256", "0" * 64)
        expected = "reference Graph path source differs"

    def analyze(*_args):
        pytest.fail("The launcher reached analysis after a Graph path check failed")

    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    with pytest.raises(ValueError, match=expected):
        launcher.run(args, spec)
    assert not list(args.bulk_root.iterdir())
