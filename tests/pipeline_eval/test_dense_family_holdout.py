from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("dense_family_holdout")


def native():
    probes = [dict(visit_index=visit, receiver_id=radio, channel=channel, actual_rf_hz=rf,
                   candidates=[visit] if radio else [])
              for visit, channel, rf in ((1, 4, 200), (2, 3, 300), (3, 4, 200))
              for radio in (0, 1)]
    return dict(source=dict(probes=probes))


def test_fold_removes_both_radios_and_preserves_empty_held_opportunities(study):
    packet = native()
    train, held = study.fold(packet, 200)
    assert [row["visit_index"] for row in train["source"]["probes"]] == [2, 2]
    assert [row["candidates"] for row in held] == [[], [1], [], [3]]
    with pytest.raises(ValueError, match="held channel"):
        study.fold(packet, 300)


def test_nomination_individually_charges_catalogue_prior_and_breaks_ties(study):
    assert [row["norad"] for row in study.rivals([8, 8, 5, 4], [50, 12, 5, 8], 100)] == [12, 50]
    assert [row["norad"] for row in study.rivals([8, 4], [50, 12], 100)] == [50]


def test_transfer_rivals_are_training_specific_and_require_budget(study):
    def row(track, *values):
        return dict(track=track, shortlist=[dict(norad=norad, log_odds=score) for norad, score in values])

    dense = [row("train1", (1, 9)), row("train2", (2, 7))]
    transfer = [row("trackA", (5, 16), (6, 7)), row("trackB", (7, 17), (8, 6))]
    data = {"DS30-0008": dict(nominations=dense), "DS30-0057": dict(nominations=transfer)}
    assert study.enroll(data, 4, (1, 2))["transfer"] == transfer[0]
    assert study.enroll(data, 4, (1, 3))["status"] == "inconclusive"
    assert study.enroll(data, 9, (1, 2))["status"] == "budget_exhausted"
