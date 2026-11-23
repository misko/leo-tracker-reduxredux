from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import geographic_rf_fold

    return geographic_rf_fold


def witness():
    tracks = [dict(key=f"{channel}-{rx}", receiver=rx, channel=channel) for channel in (2, 4) for rx in (1, 2)]
    observations = [dict(t) for t in tracks]
    # This original observation remains in the scale despite lacking a Graph track.
    observations.append(dict(receiver=1, channel=4))
    points = [dict(side="inside" if i < 48 else "exterior", xy_km=[0, i],
                   owners={t["key"]: 42 for t in tracks}) for i in range(96)]
    terms = [[0., 0., 0., 0.] for _ in points]
    terms[0] = [4., 4., 10., 10.]
    terms[1] = [1., 1., 20., 20.]
    terms[48] = [21., 21., 14., 8.]
    terms[49] = [18., 18., 25., 25.]
    return dict(tracks=tracks, observations=observations), points, terms


def test_reciprocal_rule_scores_the_same_pair_on_each_held_antenna(trial):
    graph, points, terms = witness()
    result = trial.crosscheck(graph, points, terms)
    assert result["fold_by_channel"] == {2: 0, 4: 1}
    first, second = result["directions"]
    assert (first["inside"]["index"], first["exterior"]["index"]) == (0, 48)
    assert (second["inside"]["index"], second["exterior"]["index"]) == (1, 49)
    assert first["held_gain"] == {"1": 2., "2": -2.}
    assert second["held_gain"] == {"1": 17., "2": 17.}
    assert first["satellite_overlap"]["inside"]["both"] == [42]
    assert result["verdict"] == "keep"
    terms[48][3] = 11.
    assert trial.crosscheck(graph, points, terms)["verdict"] == "possible_withhold"
    terms[48][3] = 10.
    assert trial.crosscheck(graph, points, terms)["verdict"] == "keep"


def test_empty_original_partition_and_exact_training_ties_abstain(trial):
    graph, points, terms = witness()
    missing = deepcopy(graph)
    missing["tracks"].pop()
    assert trial.crosscheck(missing, points, terms)["verdict"] == "abstain_empty"
    terms[1][:2] = terms[0][:2]
    result = trial.crosscheck(graph, points, terms)
    assert result["verdict"] == "abstain_tie"
    assert result["directions"][0]["training_gap"]["inside"] == 0
    assert "held_gain" not in result["directions"][0]


def test_nomination_requires_original_side_and_finite_training_scores(trial):
    _, points, _ = witness()
    values = [0.] * 96
    values[0] = float("nan")
    with pytest.raises(ValueError, match="finite original"):
        trial.nominate(points, values, "inside")
    with pytest.raises(ValueError, match="48-point side"):
        trial.nominate(points[1:], values[1:], "inside")
