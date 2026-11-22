import platform

import numpy as np
import pytest

from leo.analysis import graph_tracklets as graph
from leo.analysis.localization_v3 import tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from tools.pipeline_eval.variants.experimental.graph_path import NativePath, build, native_paths, pack


pytestmark = pytest.mark.skipif(platform.machine() != "x86_64", reason="x86-64 Graph experiment")


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp("graph-native") / "graph-path.so"
    build(path)
    return path


def assert_same(native, reference):
    assert native is not None
    for a, b in zip(native[:3], reference[:3], strict=True):
        assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
    assert native[3].hex() == reference[3].hex()


def test_canonical_tie_order_and_next_enabled_path(library):
    times = np.array([0., 1., 1., 2., 3.])
    values = times.copy()
    config = TrackConfig(min_points=3, min_span_s=2., track_penalty=0.)
    original = graph._graph(times, values, config)
    packed = pack(times, original)
    native = NativePath(library)
    available = np.ones(len(times), dtype=bool)
    enabled = np.ones(len(original[0]), dtype=bool)
    reference = graph._best_path(times, values, original, available, enabled, config)
    assert 1 in reference[0] and 2 not in reference[0]
    assert_same(native.solve(packed, values, available, enabled, config), reference)
    available[1] = False
    enabled[reference[2]] = False
    reference = graph._best_path(times, values, original, available, enabled, config)
    assert_same(native.solve(packed, values, available, enabled, config), reference)


def test_ordered_reference_parity_over_dense_masks_and_aliases(library):
    rng = np.random.default_rng(51)
    native = NativePath(library)
    cfg = TrackConfig(max_slope_hz_s=8000)
    times = np.arange(350) * .19
    truth = 105000. - 2700. * times + 0.8 * times**2
    values = graph._wrap(truth + rng.normal(0, 38, len(times)), cfg.alias_spacing_hz)
    original = graph._graph(times, values, cfg)
    packed = pack(times, original)
    for cutoff in (.0, .10, .25, .50, 1.0):
        available = rng.random(len(times)) > cutoff
        enabled = rng.random(len(original[0])) >= cutoff
        result = native.solve(packed, values, available, enabled, cfg)
        assert_same(result, graph._best_path(times, values, original, available, enabled, cfg))


def test_track_preparation_uses_the_same_lane_and_finalization(library):
    t = np.arange(125) * .5
    cfg = TrackConfig()
    y = graph._wrap(112000. - 500. * t + 3. * t**2, cfg.alias_spacing_hz)
    control = tracks.fit_lane(t, y, cfg)
    with native_paths(library, verify=True) as metrics:
        result = tracks.fit_lane(t, y, cfg)
        assert metrics["packed_lanes"] == 1
        assert metrics["native_paths"] == metrics["verified_paths"] > 0
        assert metrics["reference_paths"] == 0
    assert result["diagnostics"] == control["diagnostics"]
    assert len(result["tracks"]) == len(control["tracks"]) == 1
    for key in ("assignment", "alias_lifts"):
        np.testing.assert_array_equal(result[key], control[key])
    for a, b in zip(result["tracks"][0]["pieces"], control["tracks"][0]["pieces"], strict=True):
        np.testing.assert_array_equal(a["indices"], b["indices"])
        assert a["coefficients_hz"].tobytes() == b["coefficients_hz"].tobytes()


def test_shape_and_admission_fallback_keeps_the_normal_track_path(library, tmp_path):
    t = 2**41 + np.arange(70) * 0.5
    y = -500 * np.arange(70, dtype=float)
    cfg = TrackConfig()
    control = tracks.fit_lane(t, y, cfg)
    fitted = tracks.fit_lane
    with native_paths(library, verify=True) as metrics:
        result = tracks.fit_lane(t, y, cfg)
        assert metrics["unpacked_lanes"] == 1 and metrics["reference_paths"] > 0
        assert metrics["native_paths"] == 0
    assert tracks.fit_lane is fitted
    np.testing.assert_array_equal(control["assignment"], result["assignment"])
    with native_paths(tmp_path / "missing.so") as metrics:
        assert metrics["unavailable"] == 1
        assert tracks.fit_lane is fitted


def test_malformed_adjacency_rejects_the_native_pack():
    time = np.array([0., 1., 2., 3., 4.])
    graph_data = graph._graph(time, time, TrackConfig())
    outgoing = graph_data[-1].copy()
    outgoing[0] = outgoing[0][::-1].copy()
    assert pack(time, (*graph_data[:-1], outgoing)) is None
