"""Pure join of admitted138 support and public recording metadata; no storage."""

import copy
import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "2026_10_10_position_error_iter159/grouping.py"
SPEC = importlib.util.spec_from_file_location("grouping159_for160", PATH)
GROUPING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GROUPING)
SEED = "position-predictive-groups-v1"


def join(saved_support, source, binding, *, group_function=GROUPING.group_support):
    """Caller must first authenticate138 receipt/claim/archive and155 binding.

    ``binding`` is the inner155 member['binding']. Immutable public capture and
    analysis hashes plus the admitted138 support receipt authenticate its rows;
    this function does not reopen samples, reconstruct observations or fit a model.
    Window evidence is not the compound observation-plus-TLE model evidence.
    All failures raise for the runner to preserve as whole-member failures.
    """
    expected = binding["expected_input_binding"]
    model = binding["model_identity"]
    session = binding["session_id"]
    if source.session_id != session or model.get("session_id", session) != session:
        raise ValueError("Public session identity differs")
    for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(source, field) != model[field]:
            raise ValueError("Public identity differs: " + field)
    if source.input_manifest_sha256 != expected["input_digest"]:
        raise ValueError("Physical input binding differs")
    if model["evidence_sha256"] != expected["evidence_digest"]:
        raise ValueError("Compound evidence binding differs")
    if source.qualified is not True or source.timing is None:
        raise ValueError("Qualified public source and timing are required")
    timing = source.timing
    if timing.session_id != session or timing.sample_rate_hz != source.sample_rate_hz:
        raise ValueError("Timing session/sample rate differs")
    # Check types before equality can accept bool or integral-looking floats.
    GROUPING.integer(source.sample_rate_hz, "sample_rate_hz", 1)
    GROUPING.integer(timing.sample_rate_hz, "timing.sample_rate_hz", 1)
    GROUPING.integer(timing.session_start_device_sample_counter, "session counter")
    GROUPING.integer(timing.first_sample_estimate_utc_ns, "UTC origin")
    if not isinstance(saved_support, dict):
        raise ValueError("Missing saved support")
    if saved_support["observation_order_signature"] != expected["observation_order_signature"]:
        raise ValueError("Original observation order/content binding differs")
    window_evidence = saved_support["window_evidence_sha256"]
    if not isinstance(window_evidence, str) or not window_evidence:
        raise ValueError("Missing admitted window evidence identity")
    identity = {field: getattr(source, field) for field in GROUPING.IDENTITY_FIELDS}
    # A copy prevents an injected grouping implementation from altering authority.
    groups = group_function(copy.deepcopy(saved_support), copy.deepcopy(identity), seed=SEED)
    return dict(
        status="complete", session_id=session, seed=SEED, identity=identity,
        input_manifest_sha256=source.input_manifest_sha256,
        analysis_manifest_sha256=source.analysis_manifest_sha256,
        observation_order_signature=saved_support["observation_order_signature"],
        window_evidence_sha256=window_evidence,
        compound_evidence_sha256=model["evidence_sha256"],
        timing=dict(session_id=timing.session_id, sample_rate_hz=timing.sample_rate_hz,
                    session_start_device_sample_counter=timing.session_start_device_sample_counter,
                    first_sample_estimate_utc_ns=timing.first_sample_estimate_utc_ns),
        grouping=groups,
        authority_scope="138 archive/receipt authentication is a mandatory caller precondition",
        interpretation="Consumed-data grouping; disjoint support is not statistical independence",
    )
