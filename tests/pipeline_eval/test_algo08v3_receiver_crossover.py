from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def crossover(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("receiver_crossover")


def packet():
    candidate = dict(candidate_rank=1, fractional_margin=.15, passed_fractional_margin_gate=True,
                     fractional_tracking_cfo_hz=-100., integer_epoch_sample=2000,
                     fractional_epoch_offset_samples=.25)
    return dict(schema_version=1, clock_anchor={"ns": 1}, delivery_clocks={"0": 45}, last_sample_counter=3600,
                source=dict(raw_recording_authority_digest="raw", analysis_manifest_sha256="analysis",
                            probes=[dict(channel=5, visit_index=0, candidates=[candidate])]),
                provenance=dict(detector_sha256="stock", run_id="stock", excluded_windows=[]))


def test_matched_opportunities_keep_signed_measurement_changes(crossover):
    stock = packet()
    alternate = deepcopy(stock)
    alternate["provenance"].update(detector_sha256="candidate", run_id="candidate")
    alternate["source"]["analysis_manifest_sha256"] = "candidate"
    winner = alternate["source"]["probes"][0]["candidates"][0]
    winner.update(fractional_tracking_cfo_hz=100., fractional_epoch_offset_samples=.5)
    audit = crossover.match_opportunities(stock, alternate)
    assert audit["opportunities"] == 1
    assert audit["signed_selection_changes"] == {
        "v3_negative": 1, "v3_residual": 1, "alternate_positive": 1, "alternate_residual": 1,
        "cfo_changed": 1, "epoch_changed": 1, "candidate_lists_changed": 1, "rank_changed": 0,
    }


@pytest.mark.parametrize("field", ["clock_anchor", "delivery_clocks", "last_sample_counter"])
def test_different_clock_authorities_are_rejected(crossover, field):
    stock, alternate = packet(), packet()
    alternate[field] = None
    with pytest.raises(ValueError, match=field):
        crossover.match_opportunities(stock, alternate)


def test_excluded_windows_and_rf_order_are_bound(crossover):
    stock, alternate = packet(), packet()
    alternate["provenance"]["excluded_windows"] = [0]
    with pytest.raises(ValueError, match="rejected windows"):
        crossover.match_opportunities(stock, alternate)
    alternate["provenance"]["excluded_windows"] = []
    alternate["source"]["probes"][0]["channel"] = 6
    with pytest.raises(ValueError, match="RF opportunity"):
        crossover.match_opportunities(stock, alternate)


def test_full_budget_adds_acquisition_solver_and_publication(crossover):
    scorer = import_module("receiver_crossover_score")
    acquisition = dict(detection_file_elapsed_s=56., complete_elapsed_s=106., complete_cpu_s=104.)
    result = scorer.density_budget(acquisition, dict(elapsed_s=44., cpu_s=43.), {
        "elapsed_s": "113", "launch_to_detections_s": "53", "terminal_to_exit_s": "3", "cpu_s": "110",
    })
    assert result["projected_elapsed_s"] == 103.
    assert result["excess_with_free_solver_elapsed_s"] == 2.5
    assert result["maximum_acquisition_elapsed_s"] == 9.5
    assert result["alternate_acquisition_cpu_lower_bound_s"] == 54.
    assert result["alternate_combined_cpu_lower_bound_excluding_publication_s"] == 97.
    assert result["v3_historical_half_cpu_s"] == 55.
