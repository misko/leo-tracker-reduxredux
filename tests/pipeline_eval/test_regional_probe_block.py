import hashlib
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import regional_reassignment as regional
from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import (
    evaluate_terminal,
    probe_layout,
)

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))
from dense_geographic_projection import Projector  # noqa: E402
from regional_probe_block import OrderedProbeScores, ProbeBlock  # noqa: E402
import regional_probe_block_binding as binding  # noqa: E402
from regional_track_scores import TrackScores  # noqa: E402


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    directory = tmp_path_factory.mktemp("regional-probe-block")
    paths = {}
    for name in ("dense_geographic_projection", "regional_track_scores", "regional_probe_block"):
        library = directory / f"{name}.so"
        subprocess.run(
            ["cc", "-std=c11", "-O3", "-fopenmp-simd", "-ffp-contract=off", "-fno-math-errno",
             "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror",
             str(HERE / f"{name}.c"), "-lm", "-o", str(library)],
            check=True,
        )
        paths[name] = library
    return paths


def test_block_matches_original_native_values_owners_and_ties(libraries, monkeypatch):
    from leo.analysis.research.phase_linear_geometry import PreparedPhaseGeometry
    from leo.analysis.research.track_catalogue_geometry import PreparedGeometry

    generator = np.random.default_rng(790)
    positions = generator.normal(size=(4, 12, 3)) * 14
    positions[..., 0] += 6900
    positions[2, :, 0] *= -1
    velocities = generator.normal(size=positions.shape)
    dp = generator.normal(size=positions.shape)
    dv = generator.normal(size=positions.shape) * .01
    for value in (positions, velocities, dp, dv):
        value[1] = value[0]
    def dot(a, b):
        return np.einsum("otj,otj->ot", a, b)

    grid = PreparedPhaseGeometry(
        PreparedGeometry(
            positions, velocities, dot(positions, positions), dot(positions, velocities)
        ),
        dp, dv, dot(dp, velocities) + dot(positions, dv), dot(positions, dp),
    )
    library = libraries["dense_geographic_projection"]
    projector = Projector(library, hashlib.sha256(library.read_bytes()).hexdigest(),
                          regional.phase_linear_frequency)
    points = [dict(latlon=[1. + i / 100, 2. - i / 200]) for i in range(4)]
    f, _, _ = projector(grid, *points[0]["latlon"])
    tracks, observations = [], []
    for i, index in enumerate(([4, 0, 2, 7, 10, 8], [1, 3, 5, 6, 9, 11], [2])):
        ids = [f"{i}-{j}" for j in index]
        receiver = 1 + i % 2
        observations.extend(dict(observation_id=oid, receiver=receiver) for oid in ids)
        rf = 11.5e9 + i * .4e9
        tracks.append(dict(times=np.asarray(index), values=rf / 11.5e9 * f[0, index],
                           observation_ids=ids, key=str(i), receiver=receiver, rf_hz=rf))
    monkeypatch.setattr(regional, "phase_linear_frequency", projector)
    monkeypatch.setattr(regional, "orbit_geometry", lambda *_: (grid, np.array([40, 20, 30, 50])))
    monkeypatch.setattr(regional, "probes", lambda _: points)
    _, original, _ = regional._prepare_probe_scores(
        dict(observations=observations, tracks=tracks, metadata=dict(anchor_utc_ns=0)),
        SimpleNamespace(satellite_numbers=range(11)), SimpleNamespace(center=(1., 2.)),
    )
    packed = TrackScores(libraries["regional_track_scores"], original)
    native = ProbeBlock(libraries["regional_probe_block"], packed)
    scalar = [packed(dict(point)) for point in points]
    assert all(row["owners"] == {"0": 40, "1": 40, "2": None} for row in scalar)
    for width in range(1, 5):
        assert native(points[:width]) == scalar[:width]
    assert native.computed == 10
    assert packed.native == 4
    with pytest.raises(ValueError, match="coordinate"):
        native([dict(latlon=[float("nan"), 2.])])
    with pytest.raises(ValueError, match="width"):
        native([*points, points[0]])


@pytest.mark.parametrize(
    ("fault", "guaranteed_only"),
    [(False, False), (True, False), (False, True)],
)
def test_early_terminal_stop_and_failed_speculative_lane(fault, guaranteed_only):
    from tests.pipeline_eval.test_regional_exterior_veto import WIDTH, fixture

    points = fixture()
    eligible, remaining = probe_layout(points, WIDTH)
    witness = next(i for i in remaining if points[i]["side"] == "inside")
    points[witness]["receiver_scores"]["1"] = 99.
    stock_calls, native_calls, visited = [], [], []

    def stock(point):
        stock_calls.append(point)
        return point

    def batch(rows):
        native_calls.append(rows)
        if fault and points[witness] in rows:
            raise ValueError("a later speculative lane had invalid geometry")
        return rows

    ordered = OrderedProbeScores(points, WIDTH, batch, stock, guaranteed_only=guaranteed_only)

    def read(point):
        visited.append(point)
        return ordered(point)["receiver_scores"]

    answer = evaluate_terminal(points, WIDTH, read)
    assert answer == evaluate_terminal(points, WIDTH, lambda p: p["receiver_scores"])
    assert answer["stop"] == "inside_score"
    assert visited == [points[i] for i in (*eligible, witness)]
    if guaranteed_only:
        assert [p for batch in native_calls for p in batch] == [points[i] for i in eligible]
    else:
        assert native_calls[-1][0] is points[witness]
        assert len(native_calls[-1]) == 4
    assert stock_calls == ([points[witness]] if fault or guaranteed_only else [])
    assert ordered.failed is fault


@pytest.mark.parametrize("fault", ["packing", "geometry", "layout", "prepare"])
def test_reusable_proof_binding_falls_back_after_one_preparation(monkeypatch, fault):
    from tests.pipeline_eval.test_regional_exterior_veto import WIDTH, fixture

    points = fixture()
    if fault == "layout":
        points.pop()
    prepare_calls, visits = [], []

    def original(point):
        visits.append(point["xy_km"])
        return point

    def prepare(*args):
        prepare_calls.append(args)
        if fault == "prepare":
            raise ValueError("Original causal input is invalid")
        return points, original, {"track_count": 12}

    class Scalar:
        def __init__(self, _, scorer):
            if fault == "packing":
                raise ValueError("Unsupported track packing")
            self.scorer = scorer
            self.native = self.fallbacks = 0

        def __call__(self, point):
            self.native += 1
            return self.scorer(point)

    class Native:
        def __init__(self, *_):
            if fault == "geometry":
                raise ValueError("Unsupported orbit geometry")
            self.computed = self.calls = 0

    @contextmanager
    def projection(_):
        yield Counter()

    kernel = SimpleNamespace(_prepare_probe_scores=prepare, evaluate_veto=object())
    monkeypatch.setattr(binding, "checked_runtime", lambda: (kernel, None))
    monkeypatch.setattr(binding, "TrackScores", Scalar)
    monkeypatch.setattr(binding, "ProbeBlock", Native)
    region = SimpleNamespace(width_km=WIDTH)
    with binding.guarded_projection(None, None, None, projection) as counts:
        if fault == "prepare":
            with pytest.raises(ValueError, match="Original causal input"):
                kernel.evaluate_veto("tracks", "catalogue", region)
            assert not counts
        else:
            result = kernel.evaluate_veto("tracks", "catalogue", region)
            expected = evaluate_terminal(points, WIDTH, lambda p: p["receiver_scores"])
            assert result == dict(expected, track_count=12)
            assert counts["block_setup_fallbacks"] == 1
            assert counts["block_positions"] == 0
            assert len(visits) == expected["probes_evaluated"]
    assert prepare_calls == [("tracks", "catalogue", region)]
