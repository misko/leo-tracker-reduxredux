import importlib
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return importlib.import_module("weak_all8_combined")


def clocks(cpu, elapsed=None):
    return dict(cpu_s=cpu, elapsed_s=cpu if elapsed is None else elapsed)


def test_disjoint_saved_scope_partitions_and_rejects_an_overlap(study):
    spans = dict(runtime_validation=clocks(.2), request_and_causal_input=clocks(.3),
                 detector_load_selection_and_seal=clocks(.1), saved_publication=clocks(3.2, 3.4))
    result = study.disjoint(clocks(4, 4.5), spans, clocks(2.4), clocks(.5))
    assert result["other_saved_publication"]["cpu_s"] == pytest.approx(.3)
    assert result["launch_receipt_and_exit"]["elapsed_s"] == pytest.approx(.5)
    assert sum(row["cpu_s"] for row in result.values()) == pytest.approx(4.)
    with pytest.raises(ValueError, match="partition"):
        study.disjoint(clocks(4), spans, clocks(2.9), clocks(.5))


def test_cost_model_applies_half_to_complete_named_scope_and_credits_only_native(study):
    model = study.price(clocks(3.2, 3.4), clocks(1.4), clocks(4.5, 4.6), clocks(10.8, 11))
    assert model["cpu_s"]["half_original"] == pytest.approx(5.4)
    assert model["cpu_s"]["separate_clock_sum"] == pytest.approx(7.7)
    assert model["cpu_s"]["gap_if_native_free"] == pytest.approx(.9)
    assert model["elapsed_s"]["room_for_acquisition"] == pytest.approx(.9)
