"""ALGO04 only adds qualified owners to the immutable published ALGO03 proof."""

import copy
import json
import math

import pytest
from test_fast_graph_position_v2 import terminal as v2_terminal

from leo.contracts.fast_graph_position import CENTER
from leo.contracts.fast_graph_position_v3 import (
    MODEL_VERSION,
    NAMESPACE,
    candidate_admission,
    published_owners,
    validate_terminal,
)


def terminal():
    incumbent = v2_terminal()
    candidate = copy.deepcopy(incumbent)
    candidate["selected"]["targets"][0]["observation_ids"].append("extra")
    for arm in ("c0", "fitted_c"):
        saved = candidate["selected"]["arms"][arm]
        saved["associated_ids"].append("extra")
        saved["owners"]["extra"] = 2
        saved["added_points"] = 2
        saved["endpoint_east_north_km"] = [0.025, 0.0]
        saved["endpoint_latlon"] = [
            CENTER[0],
            CENTER[1] + 0.025 / (111.32 * math.cos(math.radians(CENTER[0]))),
        ]
    candidate["position"] = dict(
        zip(
            ("latitude_deg", "longitude_deg"),
            candidate["selected"]["arms"]["fitted_c"]["endpoint_latlon"],
            strict=True,
        )
    )
    return dict(
        schema_version=3,
        kind=incumbent["kind"],
        model_version=MODEL_VERSION,
        input_sha256=incumbent["input_sha256"],
        session_id=incumbent["session_id"],
        state="complete",
        incumbent=incumbent,
        candidate=candidate,
        decision="ALGO04_additive",
        position=copy.deepcopy(candidate["position"]),
        incumbent_seconds=incumbent["total_seconds"],
        numerical_seconds=25.0,
        total_seconds=incumbent["total_seconds"] + 25.0,
        reference_usage="none",
        future_TLE_used=False,
        matched_c_inputs=True,
        selected_arm="fitted_c",
    )


def test_separate_major_preserves_incumbent_and_paired_additive_owners():
    doc = terminal()
    before = json.dumps(doc["incumbent"], sort_keys=True)
    assert validate_terminal(doc, input_sha256="sha256:input") is doc
    assert json.dumps(doc["incumbent"], sort_keys=True) == before
    assert MODEL_VERSION == "algo04-causal-numerical-v1"
    assert NAMESPACE == "fast-scan-graph-position-v3"
    assert published_owners(doc["incumbent"], "c0") == {"old": 1, "new": 2}


@pytest.mark.parametrize(
    "failure",
    [
        "owner",
        "loss",
        "baseline",
        "session",
        "input",
        "position",
        "runtime",
        "gps",
        "future",
        "arm",
        "model",
    ],
)
def test_candidate_never_replaces_incumbent_or_changes_persisted_identity(failure):
    doc = terminal()
    candidate = doc["candidate"]
    if failure == "owner":
        candidate["selected"]["targets"][0]["norad"] = 3
        for arm in ("c0", "fitted_c"):
            candidate["selected"]["arms"][arm]["owners"].update(new=3, extra=3)
    elif failure == "loss":
        candidate["selected"]["targets"][0]["observation_ids"] = ["extra"]
        for arm in ("c0", "fitted_c"):
            saved = candidate["selected"]["arms"][arm]
            del saved["owners"]["new"]
            saved["associated_ids"].remove("new")
            saved["added_points"] = 1
    elif failure == "baseline":
        candidate["baseline"]["elapsed_seconds"] = 101.0
    elif failure == "session":
        candidate["session_id"] = "other"
    elif failure == "input":
        candidate["input_sha256"] = "other"
    elif failure == "position":
        doc["position"] = doc["incumbent"]["position"]
    elif failure == "runtime":
        doc["numerical_seconds"] = 1201.0
        doc["total_seconds"] = doc["incumbent_seconds"] + 1201.0
    elif failure == "gps":
        doc["reference_usage"] = "GPS"
    elif failure == "future":
        doc["future_TLE_used"] = True
    elif failure == "arm":
        doc["selected_arm"] = "c0"
    elif failure == "model":
        doc["model_version"] = doc["incumbent"]["model_version"]
    with pytest.raises(ValueError):
        validate_terminal(doc, input_sha256="sha256:input")


def test_historical_read_guard_failure_preserves_exact_incumbent_fallback():
    doc = terminal()
    old = doc["incumbent"]
    old.update(decision="ALGO02_fallback", selected=None)
    old["read_audit"]["verified"] = False
    doc.update(decision="ALGO03_fallback", position=copy.deepcopy(old["position"]))
    assert validate_terminal(doc, input_sha256="sha256:input") is doc
    admitted, reason = candidate_admission(old, doc["candidate"])
    assert not admitted and "historical" in reason
    doc.update(decision="ALGO04_additive", position=doc["candidate"]["position"])
    with pytest.raises(ValueError, match="historical"):
        validate_terminal(doc, input_sha256="sha256:input")


def test_failed_candidate_may_be_omitted_but_fallback_position_must_be_exact():
    doc = terminal()
    doc.update(
        candidate=None,
        decision="ALGO03_fallback",
        position=copy.deepcopy(doc["incumbent"]["position"]),
    )
    assert validate_terminal(doc, input_sha256="sha256:input") is doc
    doc["position"]["latitude_deg"] += 0.001
    with pytest.raises(ValueError, match="exact ALGO03"):
        validate_terminal(doc, input_sha256="sha256:input")


def test_unqualified_v3_terminal_cannot_publish_a_position():
    doc = terminal()
    doc["state"] = "failed"
    with pytest.raises(ValueError, match="cannot publish"):
        validate_terminal(doc, input_sha256="sha256:input")


def test_fallback_source_support_must_match_actual_published_baseline_owners():
    doc = terminal()
    old = doc["incumbent"]
    old.update(decision="ALGO02_fallback", selected=None)
    old["source_support"]["c0"]["owners"] = {"fabricated": 9}
    admitted, reason = candidate_admission(old, doc["candidate"])
    assert not admitted and reason == "incumbent_ownership_not_provable"
    with pytest.raises(ValueError, match="published baseline"):
        published_owners(old, "c0")
