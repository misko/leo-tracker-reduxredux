from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def radio(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("radio_epoch")


def test_pays_empty_core_lanes_and_keeps_history_separate_by_receiver(radio):
    def probe(seconds, receiver):
        return dict(valid_start_counter=int(seconds * 10_000_000), receiver_id=receiver,
                    channel=5, actual_rf_hz=12e9, candidates=[])

    probes = [probe(s, r) for s in (0, 7.9, 8, 9, 17) for r in (0, 1)]
    result = radio.blocks(probes, 0, 190_000_000, [4, 7, 8])
    left, right, later = result
    assert left.key[:3] == (1, 0, 5)
    assert left.core == {4, 6}
    assert left.owner_rows == (0,)
    assert left.paid == {0, 2, 4, 6}
    assert right.core == {5, 7}
    assert right.paid == {1, 3, 5, 7}
    assert later.paid == {6, 8}


def test_only_sharing_paid_lanes_not_nuisance_per_epoch(radio):
    choices = [
        radio.Block((0, 0), frozenset({0}), frozenset({0, 1}), (0, 1), frozenset({"a"})),
        radio.Block((1, 1), frozenset({2}), frozenset({1, 2}), (2, 3), frozenset({"b"})),
        radio.Block((2, 0), frozenset({3}), frozenset({2, 3}), (4, 5), frozenset({"b"})),
    ]
    rng = np.random.default_rng(910)
    designs = [rng.normal(size=(6, 5)), rng.normal(size=(6, 6))]
    result = radio.select(choices, designs, 3)
    best = result["best"]
    assert best["lanes"] == 3 and best["strata"] == ["a", "b"]
    actual = [j for i in best["indices"] for j in choices[i].owner_rows]
    direct = []
    for m, w in zip(designs, radio.whitening(result["full_information"]), strict=True):
        d = m[actual]
        direct.append(np.linalg.eigvalsh(w @ radio.profile(d.T @ d, 2, unpenalized=1) @ w)[0])
    assert best["fractions"] == pytest.approx(direct)
    assert best["fraction"] <= result["upper_bound"] + 1e-10
