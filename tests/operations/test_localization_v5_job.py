from copy import deepcopy

import pytest

from leo.analysis.localization_v4 import native_bound
from leo.contracts import localization_v3, localization_v5
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v5_job import execute, make_request, validate_request
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store
from leo.storage.localization_v5 import LocalizationV5Store
from tests.analysis.test_localization_v4_native import native_manifest as native_manifest
from tests.localization_v3_fixture import evidence_fixture
from tests.operations.test_localization_v3_job import request_fixture


def saved(request):
    evidence, pngs = evidence_fixture()
    evidence["model_version"] = localization_v5.MODEL
    evidence["identity"] = request["job"]["identity"]
    evidence["provenance"].update(
        request_sha256=canonical_digest(request),
        algorithm=localization_v5.MODEL,
        initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY,
        native_backend=dict(
            manifest=request["backend_manifest"],
            manifest_sha256=canonical_digest(request["backend_manifest"]),
            receipts=[],
        ),
    )
    if 'annotation_training_policy' in request:
        evidence['provenance']['annotation_training_policy'] = deepcopy(
            request['annotation_training_policy'])
        if (request['annotation_training_policy']['id']
                == localization_v5.ANNOTATION_FALLBACK_POLICY):
            from leo.operations.localization_v5_training import _counts

            evidence['provenance']['annotation_training_work'] = dict(
                schema_version=1, policy=deepcopy(request['annotation_training_policy']),
                policy_sha256=canonical_digest(request['annotation_training_policy']),
                receipts=[], counts=_counts([]))
    receipt = LocalizationV5Store(request["job"]["output_root"]).save(evidence, pngs)
    return evidence, receipt


def test_request_owns_algorithm_namespace_and_does_not_mutate_v3(native_manifest, tmp_path):
    original = request_fixture(tmp_path)
    before = deepcopy(original)
    request = make_request(original, native_manifest)
    assert original == before
    assert request["algorithm"] == localization_v5.MODEL
    assert request["job"]["identity"]["run_id"].startswith("v5-")
    assert request == make_request(original, native_manifest)
    assert validate_request(request) is request
    with pytest.raises(ValueError):
        localization_v3.validate_evidence(saved(request)[0])


def test_v5_store_and_publication_have_native_identity(native_manifest, tmp_path):
    request = make_request(request_fixture(tmp_path), native_manifest)
    _, receipt = saved(request)
    run = request["job"]["identity"]["run_id"]
    assert receipt["receipt"]["model_version"] == localization_v5.MODEL
    with pytest.raises(FileNotFoundError):
        LocalizationV3Store(request["job"]["output_root"]).load(run)
    result = execute(request, native_manifest=native_manifest, receipts=tmp_path / "unused",
                     resume_only=True)
    assert result["resumed"] and result["status"] == "complete"
    assert result["publication"]["implementation_model"] == localization_v5.MODEL
    assert result["publication"]["terminal_sha256"] == receipt["sha256"]
    publication = FastStandardAnalysisStore(request["job"]["output_root"]).detail(run)
    assert publication["state"] == "complete"
    assert not (tmp_path / "unused").exists()


def test_resume_checks_saved_backend_and_algorithm_without_native_artifacts(
    native_manifest, tmp_path, monkeypatch
):
    request = make_request(request_fixture(tmp_path), native_manifest)
    saved(request)

    def forbidden(*args, **kwargs):
        raise AssertionError("Resume must not load, build, or hash native artifacts")

    monkeypatch.setattr(native_bound, "digest", forbidden)
    monkeypatch.setattr(native_bound, "provider", forbidden)
    monkeypatch.setattr(native_bound, "build", forbidden)
    result = execute(request, native_manifest=native_manifest, receipts=tmp_path / "unused",
                     resume_only=True)
    assert result["resumed"]
    changed = deepcopy(request)
    changed["job"]["title"] = "other"
    with pytest.raises(ValueError, match="different native request"):
        execute(changed, native_manifest=native_manifest, receipts=tmp_path / "unused",
                resume_only=True)
    changed = deepcopy(request)
    changed["algorithm"] = localization_v3.MODEL
    with pytest.raises(ValueError, match="ALGO07v5 request"):
        validate_request(changed)


def test_native_backend_binding_and_cross_version_resume_rejected(native_manifest, tmp_path):
    original = request_fixture(tmp_path)
    request = make_request(original, native_manifest)
    changed = deepcopy(native_manifest)
    changed["compiler_version"] += "different"
    with pytest.raises(ValueError, match="manifest differs"):
        execute(request, native_manifest=changed, receipts=tmp_path / "unused", resume_only=True)
    evidence, pngs = evidence_fixture()
    evidence["identity"] = request["job"]["identity"]
    LocalizationV3Store(original["output_root"]).save(evidence, pngs)
    with pytest.raises(ValueError, match="No committed"):
        execute(request, native_manifest=native_manifest, receipts=tmp_path / "unused",
                resume_only=True)
    evidence["model_version"] = localization_v5.MODEL
    with pytest.raises(ValueError, match="provenance"):
        localization_v5.validate_evidence(evidence)


@pytest.mark.parametrize('field,value', [
    ('algorithm', 'algo07v4-native-v1'), ('initial_control_policy', 'other'),
    ('schema_version', 2),
])
def test_v5_request_rejects_different_policy_or_version(native_manifest, tmp_path, field, value):
    request = make_request(request_fixture(tmp_path), native_manifest)
    request[field] = value
    with pytest.raises(ValueError, match='ALGO07v5 request'):
        validate_request(request)


def test_fresh_v5_job_injects_process_bound_and_keeps_full_ports(
    native_manifest, tmp_path, monkeypatch
):
    from leo.analysis.localization_v4.backend import ProcessBound
    from leo.application import localization_v3_engine as engine
    from leo.operations import localization_v3_job as job

    request = make_request(request_fixture(tmp_path), native_manifest)
    monkeypatch.setattr(job, "read_bound", lambda record: (
        {"source": {"session_id": "session"}} if record == request["job"]["native_input"]
        else {"config": {}}
    ))

    def run(*args, **kwargs):
        ports = kwargs["execution"]
        assert isinstance(ports.bound, ProcessBound)
        from leo.analysis.localization_v5.initial_control import initial_control
        assert ports.initial_control is initial_control
        assert ports.map_initial_branches is not None
        assert ports.map_annotation_training is not None
        assert ports.map_grid_batches is not None
        return {"status": "no_active_curvature"}

    monkeypatch.setattr(engine, "run_native", run)
    result = execute(request, native_manifest=native_manifest, receipts=tmp_path / "receipts")
    assert result["status"] == "no_active_curvature" and not result["published"]


def test_saved_activation_receipt_includes_evidence_projection_calls(
    native_manifest, tmp_path, monkeypatch
):
    from leo.application import localization_v3_engine as engine
    from leo.application import localization_v3_result as projection
    from leo.operations import localization_v3_job as job
    from tests.analysis.test_localization_v4_native import sample

    request = make_request(request_fixture(tmp_path), native_manifest)
    evidence, pngs = evidence_fixture()
    holder = {}
    monkeypatch.setattr(job, "read_bound", lambda record: (
        {"source": {"session_id": "session"}} if record == request["job"]["native_input"]
        else {"config": {}}
    ))
    monkeypatch.setattr(job, "source_bindings", lambda: {})

    def run(*args, **kwargs):
        holder["bound"] = kwargs["execution"].bound
        holder["bound"](*sample())
        return dict(status="figures_ready", products=pngs)

    def project(*args, **kwargs):
        assert kwargs["provenance"]["native_backend"]["receipts"][0]["counts"]["calls"] == 1
        holder["bound"](*sample())
        evidence.update(model_version=localization_v5.MODEL,
                        identity=kwargs["identity"], provenance=kwargs["provenance"])
        return evidence

    monkeypatch.setattr(engine, "run_native", run)
    monkeypatch.setattr(projection, "_build_evidence", project)
    result = execute(request, native_manifest=native_manifest, receipts=tmp_path / "receipts")
    assert result["status"] == "complete"
    run_id = request["job"]["identity"]["run_id"]
    saved_evidence = LocalizationV5Store(request["job"]["output_root"]).load(run_id)["evidence"]
    counts = saved_evidence["provenance"]["native_backend"]["receipts"][0]["counts"]
    assert counts["calls"] == counts["activated"] == 2
