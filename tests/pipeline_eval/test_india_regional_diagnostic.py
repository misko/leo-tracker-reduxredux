from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def diagnostic(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import india_regional_diagnostic

    return india_regional_diagnostic


def test_handoff_requires_original_normalized_graph_root_and_causal_cutoff(diagnostic, tmp_path):
    from prepared_exterior import PreparedExterior

    tracks = {"metadata": {"causal_cutoff_utc_ns": 42}}
    reader = SimpleNamespace(root=tmp_path)
    causal = object()
    handoff = PreparedExterior(reader.root, tracks, 42, causal)
    assert handoff.match(tracks, reader) is causal
    assert handoff.match(deepcopy(tracks), reader) is None
    assert handoff.match(tracks, SimpleNamespace(root=tmp_path / "other")) is None
    tracks["metadata"]["causal_cutoff_utc_ns"] += 1
    assert handoff.match(tracks, reader) is None


def test_probe_maxima_keep_pooled_and_receiver_signs_independent(diagnostic):
    points = [dict(side=side, xy_km=[i / 10., north], latlon=[0., 0.], owners={"arc": 42},
                   score=base - i/100., receiver_scores={"1": rx1 - i/100., "2": rx2 - i/100.})
              for side, north, base, rx1, rx2 in (("inside", 12., 4., 1., 2.), ("exterior", 15.625, 7., 9., 1.))
              for i in range(48)]
    result = diagnostic.maxima(points, 25.)
    assert result["pooled"]["sampled_maximum"] == "exterior"
    assert result["receivers"]["1"]["exterior_gain"] == 8.
    assert result["receivers"]["2"]["exterior_gain"] == -1.
    assert result["pooled"]["exterior"]["north_face_clearance_km"] == -3.125
    assert result["pooled"]["exterior"]["runner_up_gap"] == pytest.approx(.01)
    with pytest.raises(ValueError, match="48-plus-48"):
        diagnostic.maxima(points[:-1], 25.)


def test_sealed_fit_comparison_requires_unchanged_proof_and_published_owners(diagnostic):
    original = dict(owners={"c0": "checked"}, status="ok", reason=None,
                    exterior_checks=[{"result": {"would_withhold": False, "receiver_points": {"1": 64}}, "cpu_s": 2.}])
    baseline = {"matched-tile": {"full-catalogue": original}}
    faster = dict(original, exterior_checks=[{"result": {"would_withhold": False, "receiver_points": {1: 64}}, "cpu_s": .35}])
    diagnostic.pair_original(baseline, faster, "matched-tile", "full-catalogue")
    faster["owners"] = {"c0": "changed"}
    with pytest.raises(ValueError, match="owners"):
        diagnostic.pair_original(baseline, faster, "matched-tile", "full-catalogue")
