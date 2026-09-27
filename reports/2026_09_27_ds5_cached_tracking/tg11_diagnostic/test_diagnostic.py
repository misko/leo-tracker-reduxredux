from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_diagnostic as diagnostic


def test_frozen_coordinates_match_authoritative_phase_one_receipt():
    config, receipt = diagnostic.config_and_receipt()
    rows = {row["case_id"]: row for row in receipt["rows"]}
    for case in config["cases"]:
        row = rows[case["case_id"]]
        decision = row["candidate_output"]["receiver_decisions"][case["receiver"]]
        expected = [decision["pair"][name] for name in ("first", "second")]
        for frozen, actual in zip(case["coordinates"], expected, strict=True):
            assert frozen["probe_index"] == actual["probe_index"]
            assert frozen["local_epoch_sample"] == actual["local_epoch_sample"]
            assert frozen["scoring_cfo_hz"] == actual["acquired_cfo_hz"]
            assert frozen["receipt_margin"] == actual["margin"]


def test_integer_cells_are_bounded_and_deterministic():
    assert diagnostic.integer_cells(6.976932380375004) == (6, 7)
    assert diagnostic.integer_cells(1116.338125172264) == (1116, 1117)
    assert diagnostic.integer_cells(2.5) == (2, 3)


def test_interpretation_rules_distinguish_search_from_statistic_mismatch():
    def coordinate(python_margin, native_margin, blind_margin, matched=False):
        return {
            "python_integer_cells": [{"margin": python_margin, "tracking_cfo_hz": 10.0}],
            "native_integer_cells": [{"margin": native_margin}],
            "blind_rerun": {"margin": blind_margin},
            "nearest_application_candidate": {"within_identity_gate": matched},
        }
    anchor = {"role": "retained_known_positive_anchor",
              "coordinates": [coordinate(.5, .5, .5), coordinate(.5, .5, .5)]}
    extra = {"role": "unadjudicated_additional_tg11_pair",
             "coordinates": [coordinate(.1, .2, .2), coordinate(.1, .2, .2)]}
    assert diagnostic.interpret([anchor, extra], .025)["conclusion"].startswith(
        "python_conditioned_score_passes"
    )
    extra["coordinates"] = [coordinate(.01, .2, .2), coordinate(.01, .2, .2)]
    assert diagnostic.interpret([anchor, extra], .025)["conclusion"].startswith(
        "native_and_python"
    )


def test_config_is_bounded_to_two_cases_four_coordinates_and_no_holdout():
    config = json.loads((HERE / "config.json").read_text())
    assert len(config["cases"]) == 2
    assert sum(len(case["coordinates"]) for case in config["cases"]) == 4
    assert not config["holdout"]
    assert config["timeout_seconds"] == 60

