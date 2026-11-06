import hashlib
import json
import signal
import sys
import time
from importlib.machinery import EXTENSION_SUFFIXES
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import (
    POLICY,
    StageDeadline,
    execute,
    runtime_versions,
    stage_deadline,
    validate_request,
)
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store
from tests.localization_v3_fixture import evidence_fixture


def test_source_bindings_include_native_binary_bytes(tmp_path, monkeypatch):
    from leo.operations.localization_v3_job import source_bindings

    folder = tmp_path / 'leo'
    folder.mkdir()
    path = folder / ('native_fixture' + EXTENSION_SUFFIXES[0])
    path.write_bytes(b'first artifact')
    monkeypatch.setitem(sys.modules, 'leo.native_fixture', SimpleNamespace(__file__=str(path)))
    first = source_bindings()['leo.native_fixture']
    assert first == dict(path=str(path), sha256=hashlib.sha256(b'first artifact').hexdigest())
    path.write_bytes(b'changed artifact')
    assert source_bindings()['leo.native_fixture'] != first


def request_fixture(tmp_path):
    evidence, _ = evidence_fixture()
    return dict(
        schema_version=1,
        execution_policy=POLICY,
        identity=evidence["identity"],
        native_input=dict(path=str(tmp_path / "absent-native.json"), sha256="sha256:" + "1" * 64),
        track_config=dict(path=str(tmp_path / "absent-config.json"), sha256="sha256:" + "2" * 64),
        tle_root=str(tmp_path / "absent-tle"),
        output_root=str(tmp_path / "outputs"),
        search_center=[37.906, -122.545],
        screen_center=[37.5, -122.0],
        scan_identities=["session"],
        title="fixture",
        evaluation_reference=None,
        runtime=runtime_versions(),
    )


def test_fresh_job_wires_owned_pair_executor(tmp_path, monkeypatch):
    from leo.application import localization_v3_engine as engine
    from leo.operations import localization_v3_job as job
    from leo.operations.localization_v3_parallel import (
        map_annotation_training,
        map_grid_batches,
        map_initial_arms,
        map_initial_branches,
        map_predictive_folds,
    )

    request = request_fixture(tmp_path)
    monkeypatch.setattr(job, 'read_bound', lambda record: (
        {'source': {'session_id': 'session'}} if record is request['native_input']
        else {'config': {}}))
    def run(*args, **kwargs):
        assert kwargs['execution'].map_initial_arms is map_initial_arms
        assert kwargs['execution'].map_initial_branches is map_initial_branches
        assert kwargs['execution'].map_predictive_folds is map_predictive_folds
        assert kwargs['execution'].map_family_arms is map_initial_arms
        assert kwargs['execution'].map_recovery_arms is map_initial_arms
        assert kwargs['execution'].map_conservative_arms is map_initial_arms
        assert kwargs['execution'].map_annotation_training is map_annotation_training
        assert kwargs['execution'].map_grid_batches is map_grid_batches
        return {'status': 'no_active_curvature'}
    monkeypatch.setattr(engine, 'run_native', run)
    result = execute(request)
    assert result['published'] is False


def save_fixture(request):
    evidence, pngs = evidence_fixture()
    evidence["provenance"]["request_sha256"] = canonical_digest(request)
    return LocalizationV3Store(request["output_root"]).save(evidence, pngs)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("execution_policy", "production"),
        ("native_input", None),
        ("screen_center", None),
        ("screen_center", [float("nan"), 0]),
        ("output_root", "/mnt/qnap01/no-write"),
        ("scan_identities", ["wrong"]),
        ("evaluation_reference", []),
        ("runtime", None),
        ("search_center", [0, 0]),
    ],
)
def test_request_rejects_ambiguous_or_unbound_execution(tmp_path, key, value):
    request = request_fixture(tmp_path)
    request[key] = value
    with pytest.raises(ValueError):
        validate_request(request)
    assert not (tmp_path / "outputs").exists()


def test_resume_publishes_without_native_inputs_archive_or_fitting(tmp_path, monkeypatch):
    import leo.operations.localization_v3_job as job

    request = request_fixture(tmp_path)
    receipt = save_fixture(request)

    def forbidden(*args):
        raise AssertionError("Resume must not read scientific inputs")

    monkeypatch.setattr(job, "read_bound", forbidden)
    first = execute(request, resume_only=True)
    assert first["status"] == "complete" and first["resumed"] is True
    assert first["publication"]["terminal_sha256"] == receipt["sha256"]
    assert execute(request)["publication"] == first["publication"]
    assert FastStandardAnalysisStore(request["output_root"]).detail("run")["state"] == "complete"


def test_resume_rejects_other_request_and_changed_runtime(tmp_path):
    request = request_fixture(tmp_path)
    save_fixture(request)
    request["title"] = "other request"
    with pytest.raises(ValueError, match="different native request"):
        execute(request)
    request["runtime"]["numpy"] = "wrong-version"
    with pytest.raises(ValueError, match="runtime differs"):
        execute(request)


def test_committed_result_with_missing_archive_does_not_restart_fitting(tmp_path):
    request = request_fixture(tmp_path)
    saved = save_fixture(request)
    # Storage corruption is injected only by this boundary test.
    root = tmp_path / "outputs/localization-v3-v1/run"
    (root / (saved["receipt"]["result_sha256"][7:] + ".zip")).unlink()
    assert LocalizationV3Store(request["output_root"]).receipt("run") == saved
    with pytest.raises(FileNotFoundError):
        execute(request)
    assert FastStandardAnalysisStore(request["output_root"]).detail("run")["state"] == "pending"


def test_resume_missing_result_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="No committed"):
        execute(request_fixture(tmp_path), resume_only=True)


def test_stage_timeout_cannot_become_a_scientific_rejection():
    before = signal.getsignal(signal.SIGALRM)
    with pytest.raises(StageDeadline), stage_deadline(0.02):
        try:
            time.sleep(1)
        except Exception:
            pytest.fail("Operational cancellation became a scientific fallback")
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == before


def test_existing_deadline_is_not_overwritten():
    with stage_deadline(10):
        with pytest.raises(RuntimeError, match="existing process timer"), stage_deadline(1):
            pass
        assert signal.getitimer(signal.ITIMER_REAL)[0] > 1


def test_input_hash_is_checked_before_decode(tmp_path):
    from leo.operations.localization_v3_job import read_bound

    path = tmp_path / "input.json"
    path.write_text(json.dumps(dict(changed=True)))
    with pytest.raises(ValueError, match="input changed"):
        read_bound(dict(path=str(path), sha256="sha256:" + "0" * 64))
