import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from inference_loader import (
    InferenceLoader,
    inference_document,
    observation_signature,
    validate_direct_metadata,
)


class PoisonReference(dict):
    def __getitem__(self, key):
        if "reference" in key or "error" in key:
            raise AssertionError("evaluation field read")
        return super().__getitem__(key)


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    return value


def digest(value):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(json_value(value), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def fixture(tmp_path):
    observations = SimpleNamespace(
        window_ids=["a", "b"],
        times_s=np.array([0.0, 1.0]),
        measured_hz=np.array([10.0, 20.0]),
        rf_hz=np.array([100.0, 200.0]),
        receiver=np.array([0, 1], dtype=np.uint8),
        channel=np.array([0, 0]),
        margin=np.array([5.0, 6.0]),
    )
    prepared = SimpleNamespace(
        observations=observations,
        evidence_sha256="windows",
        start_utc_ns=1_000_000_000_000,
        bootstrap_tracks=["track"],
    )
    snapshot = SimpleNamespace(digest="snapshot")
    catalogue = SimpleNamespace(
        names=["STARLINK A", "OTHER", "STARLINK B"], satellite_numbers=np.array([11, 99, 22])
    )
    bank = SimpleNamespace(numbers=np.array([11, 22]))
    calls = []
    source = SimpleNamespace(input_manifest_sha256="input", analysis_manifest_sha256="analysis")

    class Store:
        def __init__(self, path):
            pass

        def load(self, session):
            assert session == "session"
            return source

        def close(self):
            pass

    class Archive:
        def __init__(self, path):
            pass

        def select_latest_before(self, cutoff):
            assert cutoff == prepared.start_utc_ns - 505_000_000_000
            return snapshot

        def read(self, selected):
            assert selected is snapshot
            return "elements"

    def build(catalogue_arg, indices, start, obs, prior, *, maximum_seconds):
        assert catalogue_arg is catalogue and indices.tolist() == [0, 2]
        assert obs is observations and maximum_seconds == 180
        calls.append("bank")
        return bank, {}

    core = SimpleNamespace(
        canonical_digest=digest,
        json_value=json_value,
        np=np,
        ScannerTrackingInputStore=Store,
        prepare_position_windows=lambda source: prepared,
        TleArchiveReader=Archive,
        exclude_labelled_starlink_debris=lambda text: (text, {}),
        parse_element_sets=lambda text: catalogue,
        RegionalPrior=lambda **prior: prior,
        HARD60_SCORE={},
        build_regional_bank=build,
    )
    evidence = digest(dict(windows="windows", tle="snapshot", candidates=[11, 22]))
    raw = PoisonReference(
        session_id="session",
        input_manifest_sha256="input",
        analysis_manifest_sha256="analysis",
        evidence_sha256=evidence,
        configuration=PoisonReference(
            prior={"radius_km": 240.0}, scores={"V16": {}}, run={}, reference_latitude_deg=999.0
        ),
        reference_latitude_deg=0.0,
        horizontal_error_m=1.0,
    )
    document = inference_document(raw)
    path = tmp_path / "document.json"
    path.write_text(json.dumps(document))
    expected = dict(
        input_digest="input",
        evidence_digest=evidence,
        observation_order_signature=observation_signature(observations, core),
        score_signature=digest(dict(prior=document["configuration"]["prior"], score={})),
        bank_signature=digest([11, 22]),
    )
    model = PoisonReference(
        input_manifest_sha256="input",
        analysis_manifest_sha256="analysis",
        evidence_sha256=evidence,
        prior_signature=digest(document["configuration"]["prior"]),
        score_signature=digest(document["configuration"]["scores"]),
        snapshot_sha256="snapshot",
        bank_signature=digest([11, 22]),
        reference_latitude_deg=0.0,
    )
    binding = dict(
        document_path="document.json",
        document_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        session_id="session",
        model_identity=model,
        expected_input_binding=expected,
    )
    namespace = {"core": core}
    exec(
        "def backend_load_case(document): raise AssertionError('historical loader called')",
        namespace,
    )
    return InferenceLoader(tmp_path, namespace["backend_load_case"]), binding, raw, calls


def test_actual_loader_reference_poison_perturbation_invariance(tmp_path):
    loader, binding, raw, calls = fixture(tmp_path)
    first = loader(binding)
    clean = inference_document(raw)
    raw["reference_latitude_deg"] = -88.0
    raw["horizontal_error_m"] = 999_999.0
    raw["configuration"]["reference_latitude_deg"] = -77.0
    binding["model_identity"]["reference_latitude_deg"] = 999.0
    assert inference_document(raw) == clean
    second = loader(binding)
    assert first["observations"] is second["observations"]
    assert first["bank"] is second["bank"] and first["identity"] == second["identity"]
    del raw["reference_latitude_deg"]
    del raw["horizontal_error_m"]
    del raw["configuration"]["reference_latitude_deg"]
    del binding["model_identity"]["reference_latitude_deg"]
    assert inference_document(raw) == clean
    third = loader(binding)
    assert third["bank"] is first["bank"] and third["identity"] == first["identity"]
    assert calls == ["bank", "bank", "bank"]
    assert not any("reference" in name or "error" in name for name in first["document"])


def test_observation_mismatch_prevents_bank_construction(tmp_path):
    loader, binding, _, calls = fixture(tmp_path)
    binding["expected_input_binding"]["observation_order_signature"] = "wrong"
    with pytest.raises(ValueError, match="observations/order"):
        loader(binding)
    assert calls == []


def test_missing_direct_metadata_fails_before_recording_admission():
    with pytest.raises(ValueError, match="snapshot"):
        validate_direct_metadata(dict(diagnostics=dict(snapshot_sha256=None, bank=None)))
    with pytest.raises(ValueError, match="bank"):
        validate_direct_metadata(dict(diagnostics=dict(snapshot_sha256="snapshot", bank=None)))
    validate_direct_metadata(
        dict(diagnostics=dict(snapshot_sha256="snapshot", bank={"retained_numbers": [1, 2]}))
    )
