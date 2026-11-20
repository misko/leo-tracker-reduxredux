from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import phase_capture as method


def track(t, lane=0):
    return SimpleNamespace(t=np.arange(t, t + 4), lane=lane, rf=11.5e9, curved=True)


def test_shared_nonlinear_phase_requires_distinct_training_tracks():
    tracks = [track(3), track(15, lane=1)]
    phase = int(np.flatnonzero(method.PHASES == -10)[0])
    cost = np.full((1, 2, len(method.PHASES)), np.inf)
    cost[0, 0, phase] = 1.0
    cost[0, 1, method.ZERO] = 1.0
    first = (0, np.array([0, 1]), cost)
    second = (1, np.array([0]), cost[:, :1])
    result = method._anchors([first, second], tracks, [[0.0, 0.0]], 2)
    assert result[0]["phase_s"] == -10.0
    assert result[0]["eligible"]
    assert not result[1]["eligible"]
    assert not method._anchors([first], tracks, [[0.0, 0.0]], 2)[0]["eligible"]


def test_anchor_check_never_scores_downstream_holdout(monkeypatch):
    checked = []
    tracks = [track(3), track(15, lane=1), track(27), track(51, lane=1)]
    phase = int(np.flatnonzero(method.PHASES == -10)[0])

    def cells(bank, row, sites, lane_state):
        checked.append(int(row.t[0]))
        result = np.full((len(sites), 2, len(method.PHASES)), np.inf)
        result[:, 0, phase] = 0.5
        result[:, 1, method.ZERO] = 3.0
        return result

    monkeypatch.setattr(method, "cells", cells)
    bank = SimpleNamespace(positions_km=np.zeros((2, 3)))
    selected, evidence = method.acquire(bank, tracks, None, 12.5)
    assert selected == {0: -10.0}
    assert checked == [3, 15, 51]
    assert evidence["downstream_held_curved_rows"] == 1
    assert set(evidence["basins"][0]["votes"]) == {0, 1}
    assert evidence["basins"][0]["held"][0]["track"] == 3


def test_zero_anchors_preserve_same_native_bank_object():
    tile = object()
    assert method._shifted(tile, None, None, {}) is tile
