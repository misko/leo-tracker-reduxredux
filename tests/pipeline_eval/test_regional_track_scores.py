from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))
from regional_track_scores import TrackScores
from tools.pipeline_eval.variants.experimental import regional_reassignment as regional


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    library = tmp_path_factory.mktemp("regional-track-kernel") / "scores.so"
    subprocess.run(["cc", "-O2", "-std=c11", "-ffp-contract=off", "-fPIC", "-shared",
                    str(HERE / "regional_track_scores.c"), "-lm", "-o", str(library)], check=True)
    return library


@pytest.mark.parametrize("mode", ["visible", "tied", "partial_horizon", "none", "float_horizon"])
def test_original_likelihood_and_owner(compiled, monkeypatch, mode):
    rng = np.random.default_rng(89)
    f = rng.normal(0, 3100, (17, 19))
    derivative = rng.normal(0, 8, f.shape)
    horizon = np.ones(f.shape, dtype=np.int8)
    if mode == "tied":
        f[0], derivative[0] = f[1], derivative[1]
    if mode == "partial_horizon":
        horizon[1, 7] = -1
    if mode == "none":
        horizon.fill(-1)
    if mode == "float_horizon":
        horizon = horizon.astype(float)
    monkeypatch.setattr(regional, "phase_linear_frequency", lambda *_: (f, horizon, derivative))
    monkeypatch.setattr(regional, "orbit_geometry", lambda *_: (object(), np.arange(30, 47)))
    monkeypatch.setattr(regional, "probes", lambda _: [dict(latlon=[40., -5.])])
    tracks = []
    obs = []
    for k, indices in enumerate((np.arange(0, 19, 2), np.arange(1, 19, 2), np.array([7]))):
        ids = [f"{k}-{index}" for index in indices]
        receiver = 1 + k % 2
        obs.extend(dict(observation_id=identity, receiver=receiver) for identity in ids)
        rf = 11.5e9 + k * 2.5e8
        tracks.append(dict(times=indices, values=(rf / 11.5e9) * f[1, indices] + 900.,
                           observation_ids=ids, key=str(k), receiver=receiver, rf_hz=rf))
    doc = dict(observations=obs, tracks=tracks, metadata=dict(anchor_utc_ns=0))
    points, original, _ = regional._prepare_probe_scores(doc, SimpleNamespace(satellite_numbers=range(21)),
                                                         SimpleNamespace(center=(40., -5.)))
    candidate = TrackScores(compiled, original)
    control = original(dict(points[0]))
    trial = candidate(dict(points[0]))
    assert trial["owners"] == control["owners"]
    assert trial["receiver_scores"] == pytest.approx(control["receiver_scores"], abs=1e-12, rel=0.)
    assert trial["score"] == pytest.approx(control["score"], abs=1e-12, rel=0.)
    assert candidate.fallbacks == int(mode == "float_horizon")
    subset = TrackScores(compiled, original, only_receiver=1)
    if mode == "float_horizon":
        with pytest.raises(ValueError, match="requires the original native score"):
            subset(dict(points[0]))
    else:
        partial = subset(dict(points[0]))
        assert partial["receiver_scores"] == {"1": trial["receiver_scores"]["1"]}
        assert partial["owners"] == {k: trial["owners"][k] for k in ("0", "2")}


@pytest.mark.parametrize("evidence", ["strict", "equality", "ext_tie", "invalid", "positive", "bad_layout"])
def test_one_receiver_terminal_veto(evidence):
    from bilateral_veto_disproof import disprove
    from tests.pipeline_eval.test_regional_exterior_veto import WIDTH, fixture, scores_at
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    points = fixture()
    first = points[0]["receiver_scores"]
    if evidence in ("strict", "equality", "invalid"):
        first["1"] = {"strict": 3., "equality": 2., "invalid": float("nan")}[evidence]
    if evidence == "ext_tie":
        scores_at(points, (30., 4.))["1"] = 2.
    if evidence == "bad_layout":
        points.pop()
    visited = []

    def score(point):
        visited.append(point)
        return point["receiver_scores"]["1"]

    original = evaluate_terminal(points, WIDTH, lambda point: point["receiver_scores"])
    result = disprove(points, WIDTH, score)
    if evidence == "strict":
        assert len(visited) == 25 and visited[-1] is points[0]
        assert result == dict(would_withhold=False, complete=False, probes_evaluated=25,
                              stop="single_receiver_inside_score")
        assert original["would_withhold"] == result["would_withhold"]
    else:
        assert result is None
        assert original["would_withhold"] == (evidence == "positive")
        assert len(visited) == {"ext_tie": 24, "bad_layout": 0}.get(evidence, 25)


def test_track_library_requires_projector(tmp_path):
    from full_short_run import main

    args = [x for name in ("recording", "archive", "region", "output", "short-binary", "regional-track-library")
            for x in ("--" + name, str(tmp_path / name))]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_nonfinite_comparisons_are_rejected():
    from regional_track_trial import same_visits

    row = dict(xy_km=[0., 0.], latlon=[40., -5.], side="inside", owners={"a": 3},
               score=1., receiver_scores={"1": 1., "2": 1.})
    with pytest.raises(ValueError, match="Nonfinite"):
        same_visits([row], [{**row, "receiver_scores": {"1": float("nan"), "2": 1.}}])


@pytest.mark.parametrize("mode", ["raw", "saved"])
def test_public_entry_binds_both_libraries(monkeypatch, tmp_path, mode):
    import json
    import full_short_run as entry

    projected = []
    monkeypatch.setattr(entry, "geographic_projection", lambda *paths: projected.extend(paths))
    monkeypatch.setattr(entry, "MixedApertureDetector", lambda *a, **k: SimpleNamespace(detector=object()))

    def publication(args, **options):
        args.output.mkdir()
        options["geographic_projector"]()

    monkeypatch.setattr(entry, "run", publication)
    flags = [x for name in ("recording", "archive", "region", "output", "geographic-library", "regional-track-library")
             for x in ("--" + name, str(tmp_path / name))]
    entry.main(flags + (["--short-binary", "short.so"] if mode == "raw" else ["--saved", "packet", "--saved-digest", "sha256:abc"]))
    result = json.loads((tmp_path / "output/full-short-recipe.json").read_bytes())
    assert result["regional_track_sha256"] == entry.TRACK_SCORES_SHA
    assert projected == [tmp_path / "geographic-library", tmp_path / "regional-track-library"]
