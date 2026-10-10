"""Synthetic public metadata only; no storage, models or reference ports."""

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

SPEC = importlib.util.spec_from_file_location("preparation160_test", Path(__file__).with_name("preparation.py"))
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


def fixture():
    source = NS(session_id="s", input_manifest_sha256="input", analysis_manifest_sha256="analysis",
                raw_recording_authority_digest="raw", radio_id="radio",
                stream_generation="adaptive-iio-0000000000000001", sample_rate_hz=10_000_000,
                qualified=True, timing=NS(session_id="s", sample_rate_hz=10_000_000,
                    session_start_device_sample_counter=2**60,
                    first_sample_estimate_utc_ns=1_800_000_000_000_000_000))
    binding = dict(session_id="s", model_identity=dict(session_id="s",
        input_manifest_sha256="input", analysis_manifest_sha256="analysis", evidence_sha256="compound"),
        expected_input_binding=dict(input_digest="input", evidence_digest="compound",
                                    observation_order_signature="original-order"))
    support = dict(observation_order_signature="original-order", window_evidence_sha256="windows-not-compound",
                   observations=0, available=0, rows=[], unavailable_reasons={})
    return support, source, binding


def test_join_fixed_seed_distinct_evidence_and_preserved_inputs():
    support, source, binding = fixture(); original = copy.deepcopy(support)
    def groups(rows, identity, *, seed):
        assert seed == "position-predictive-groups-v1"
        assert identity["stream_generation"] == source.stream_generation
        assert identity["sample_rate_hz"] == 10_000_000
        rows["rows"].append("mutation of supplied copy")
        return {"synthetic": True}
    result = PREP.join(support, source, binding, group_function=groups)
    assert result["status"] == "complete" and support == original
    assert result["window_evidence_sha256"] != result["compound_evidence_sha256"]
    assert result["timing"]["session_start_device_sample_counter"] == 2**60


@pytest.mark.parametrize("fault", ["session", "model-session", "input", "analysis", "input-binding",
    "compound", "qualified", "timing", "timing-session", "timing-rate", "float-rate",
    "bool-counter", "order", "window-evidence"])
def test_bad_authority_fails_before_grouping(fault):
    support, source, binding = fixture()
    if fault == "session": source.session_id = "other"
    if fault == "model-session": binding["model_identity"]["session_id"] = "other"
    if fault == "input": source.input_manifest_sha256 = "other"
    if fault == "analysis": source.analysis_manifest_sha256 = "other"
    if fault == "input-binding": binding["expected_input_binding"]["input_digest"] = "other"
    if fault == "compound": binding["expected_input_binding"]["evidence_digest"] = "other"
    if fault == "qualified": source.qualified = False
    if fault == "timing": source.timing = None
    if fault == "timing-session": source.timing.session_id = "other"
    if fault == "timing-rate": source.timing.sample_rate_hz = 2_500_000
    if fault == "float-rate": source.sample_rate_hz = 10_000_000.0
    if fault == "bool-counter": source.timing.session_start_device_sample_counter = True
    if fault == "order": support["observation_order_signature"] = "other"
    if fault == "window-evidence": support["window_evidence_sha256"] = ""
    with pytest.raises(ValueError):
        PREP.join(support, source, binding, group_function=lambda *a, **k: pytest.fail("grouping admitted"))


def test_real_grouping_retains_every_row_and_rejects_missing_support():
    support, source, binding = fixture()
    support["rows"] = [dict(index=i, visit_index=i, receiver=i%2, probe_index=0,
        window_id=f"w{i}", candidate_id=f"c{i}", support_status="available", support_reason=None,
        device_sample_start=2**60+i*100, device_sample_end=2**60+i*100+10) for i in range(32)]
    support.update(observations=32, available=32)
    result = PREP.join(support, source, binding)
    assert sorted(result["grouping"]["folds"]["0"]+result["grouping"]["folds"]["1"]) == list(range(32))
    support["available"] = 31
    with pytest.raises(ValueError, match="Incomplete support"):
        PREP.join(support, source, binding)


def test_unqualified_stream_or_single_fold_is_not_replaced():
    support, source, binding = fixture()
    support.update(observations=1, available=1, rows=[dict(index=0, visit_index=1,
        receiver=0, probe_index=0, window_id="w", candidate_id="c", support_status="available",
        support_reason=None, device_sample_start=1, device_sample_end=2)])
    source.stream_generation = ""
    with pytest.raises(ValueError, match="authoritative identity"):
        PREP.join(support, source, binding)
    source.stream_generation = "stream"
    with pytest.raises(ValueError, match="nonempty"):
        PREP.join(support, source, binding)
