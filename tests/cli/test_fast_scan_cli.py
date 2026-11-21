import json
import pytest

from typer.testing import CliRunner

from leo.cli.app import create_cli


def test_offline_command_composes_explicit_mode_and_workers(monkeypatch, tmp_path):
    import leo.processing.fast_scan as processing

    calls = []

    def replay(recording, **kwargs):
        calls.append((recording, kwargs))
        return {"counts": {"processed": 2}, "points": [1]}

    monkeypatch.setattr(processing, "process_recording", replay)
    result = CliRunner().invoke(
        create_cli(),
        [
            "scan",
            "analyze-fast",
            str(tmp_path / "raw"),
            "--bulk-root",
            str(tmp_path / "bulk"),
            "--database-url",
            "postgresql:///test",
            "--workers",
            "8",
            "--mode",
            "shadow",
            "--export-tracking-input",
        ],
    )
    assert result.exit_code == 0, result.exception
    assert json.loads(result.stdout) == {"counts": {"processed": 2}}
    assert calls[0][1]["workers"] == 8
    assert calls[0][1]["policy"].mode == "shadow"
    assert calls[0][1]["export_tracking_input"] is True


def test_invalid_mode_never_queues_work(monkeypatch, tmp_path):
    import leo.processing.fast_scan as processing

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid policy must not queue work")

    monkeypatch.setattr(processing, "process_recording", forbidden)
    result = CliRunner().invoke(
        create_cli(),
        [
            "scan",
            "analyze-fast",
            str(tmp_path),
            "--bulk-root",
            str(tmp_path),
            "--database-url",
            "postgresql:///test",
            "--mode",
            "invalid",
        ],
    )
    assert result.exit_code != 0
    assert not isinstance(result.exception, AssertionError)


def test_auto_discovery_waits_for_terminal_and_does_not_repeat_completion(tmp_path):
    from leo.cli.fast_scan import discover_automatic
    from leo.contracts.digests import canonical_digest
    from leo.storage.continuous_window import write_checkpoint
    from leo.storage.fast_scan import FastScanStore
    from tests.contracts.test_continuous_window_contracts import checkpoint

    raw = tmp_path / "raw"
    folder = raw / "run"
    folder.mkdir(parents=True)
    store = FastScanStore(tmp_path / "bulk")
    config = {"targets": [{"edge": "lower"}]}
    cp = checkpoint().model_copy(update={"configuration": config,
        "configuration_sha256": canonical_digest(config), "state": "running"})
    write_checkpoint(folder, cp)
    assert discover_automatic(raw, store) == []
    assert store.automatic_status("run")["state"] == "recording"
    cp = cp.model_copy(update={"state": "stopped", "captured_windows": 8,
        "durable_windows": 8, "device_terminal": {"state": 1, "error": 0},
        "host_restoration": {"fastlock_inactive": True}})
    write_checkpoint(folder, cp)
    assert discover_automatic(raw, store) == [folder]
    store.update_automatic("run", state="tracking")
    assert discover_automatic(raw, store) == [folder]
    store.update_automatic("run", state="complete")
    assert discover_automatic(raw, store) == []


def test_published_alias_cannot_mask_owned_checkpoint_or_fail_healthy_capture(tmp_path):
    from leo.cli.fast_scan import capture_health_by_id, discover_automatic
    from leo.contracts.digests import canonical_digest
    from leo.storage.continuous_window import write_checkpoint
    from leo.storage.fast_scan import FastScanStore
    from tests.contracts.test_continuous_window_contracts import checkpoint

    raid, staging = tmp_path / "raid", tmp_path / "staging"
    recording = raid / "run"
    recording.mkdir(parents=True)
    staging.mkdir()
    alias = staging / "run"
    alias.symlink_to(recording)
    store = FastScanStore(tmp_path / "bulk")
    config = {"targets": [{"edge": "lower"}]}
    cp = checkpoint().model_copy(update={"configuration": config,
        "configuration_sha256": canonical_digest(config), "state": "stopped",
        "captured_windows": 8, "durable_windows": 8,
        "device_terminal": {"state": 1, "error": 0}, "host_restoration": {"fastlock_inactive": True}})
    write_checkpoint(recording, cp)
    original = (recording / "run.json").read_bytes()
    assert capture_health_by_id([raid, staging])["run"]["state"] == "stopped"
    assert capture_health_by_id([staging]) == {}
    modified = (recording / "run.json").stat().st_mtime_ns
    warning = "ValueError: continuous run must be one owned directory"
    failure = "Interrupted capture: no acquisition owner and stale checkpoint; retained IQ was not changed"
    evidence = dict(acquisition_owner_absent=True, checkpoint_updated_utc_ns=modified,
                    checked_utc_ns=modified + 1)
    original_status = dict(state="failed", failure=failure, discovery_warning=warning,
                           reconciliation=evidence)
    for changes in ({"failure": "analysis crashed"}, {"discovery_warning": "invalid JSON"},
                    {"reconciliation": {**evidence, "checkpoint_updated_utc_ns": modified - 1}},
                    {"reconciliation": {**evidence, "acquisition_owner_absent": False}}):
        status = store.update_automatic("run", **{**original_status, **changes})
        assert discover_automatic(raid, store, [staging]) == []
        assert store.automatic_status("run") == status
    status = store.update_automatic("run", **original_status)
    assert discover_automatic(raid, store, []) == []
    assert discover_automatic(raid, store, [staging]) == [recording]
    admitted = store.automatic_status("run")
    assert admitted["state"] == "queued" and admitted["captured_windows"] == 8
    assert admitted["reconciliation"] == evidence
    assert admitted["archive_alias_recovery"]["previous_status_updated_utc_ns"] == status["updated_utc_ns"]
    assert (recording / "run.json").read_bytes() == original
    for invalid in ({"durable_windows": 0}, {"device_terminal": {"state": 0, "error": 5}},
                    {"host_restoration": {"fastlock_inactive": False}}):
        write_checkpoint(recording, cp.model_copy(update=invalid))
        changed = (recording / "run.json").stat().st_mtime_ns
        invalid_status = store.update_automatic("run", **{**original_status, "reconciliation":
            {**evidence, "checkpoint_updated_utc_ns": changed, "checked_utc_ns": changed + 1}})
        assert discover_automatic(raid, store, [staging]) == []
        assert store.automatic_status("run") == invalid_status
    write_checkpoint(recording, cp)
    modified = (recording / "run.json").stat().st_mtime_ns
    original_status["reconciliation"].update(checkpoint_updated_utc_ns=modified, checked_utc_ns=modified + 1)
    status = store.update_automatic("run", **original_status, standard_algorithm="ALGO08")
    assert discover_automatic(raid, store, [staging]) == []
    assert store.automatic_status("run") == status


def test_automatic_failure_never_reports_complete(monkeypatch, tmp_path):
    import threading

    import pytest

    import leo.processing.fast_scan as processing
    from leo.cli.fast_scan import process_automatic
    from leo.storage.fast_scan import FastScanStore

    def failed(*args, **kwargs):
        raise ValueError("broken IQ")
    monkeypatch.setattr(processing, "process_recording", failed)
    store = FastScanStore(tmp_path / "bulk")
    with pytest.raises(ValueError, match="broken IQ"):
        process_automatic(tmp_path / "recording", store=store, database_url="unused",
                          standard_command=[], glrt_lock=threading.Lock(), standard_mode='algo07')
    assert store.automatic_status("recording")["state"] == "failed"


def test_automatic_resumes_standard_slices_without_recomputing_glrt(monkeypatch, tmp_path):
    import threading
    from types import SimpleNamespace

    import leo.cli.fast_scan as cli
    import leo.processing.fast_scan as processing
    from leo.storage.fast_scan import FastScanStore

    store = FastScanStore(tmp_path / "bulk")
    store.update_automatic("recording", state="tracking", run_id="run", session_id="session")
    def forbidden(*args, **kwargs):
        raise AssertionError("sealed GLRT must not be repeated")
    monkeypatch.setattr(processing, "process_recording", forbidden)
    calls = []
    def standard(command, **kwargs):
        calls.append(command)
        workspace = store.automatic_workspace("recording")
        (workspace / "adapter-receipt.json").write_text(json.dumps({
            "analysis_complete": len(calls) == 2, "standard_stages": {"regional": True}}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cli.subprocess, "run", standard)
    result = cli.process_automatic(tmp_path / "recording", store=store, database_url="unused",
        standard_command=["python", "bridge"], glrt_lock=threading.Lock(),standard_mode='legacy')
    assert len(calls) == 2
    assert "--full" in calls[0]
    assert result["state"] == "complete"


def test_algo07_is_standard_and_does_not_launch_the_legacy_pipeline(monkeypatch,tmp_path):
    import threading
    import leo.cli.fast_scan as cli
    import leo.processing.fast_scan as processing
    from leo.storage.fast_scan import FastScanStore
    store=FastScanStore(tmp_path/'bulk')
    store.update_automatic('recording',state='tracking',run_id='run',session_id='session')
    def forbidden(*a,**k):raise AssertionError('must not repeat GLRT or legacy analysis')
    monkeypatch.setattr(processing,'process_recording',forbidden)
    monkeypatch.setattr(cli.subprocess,'run',forbidden)
    class Reader:
        state='pending'
        def detail(self,run_id):return dict(state=self.state,terminal_sha256='sha256:terminal')
    reader=Reader()
    for expected in ('tracking','complete'):
        result=cli.process_automatic(tmp_path/'recording',store=store,database_url='unused',
            standard_command=[],glrt_lock=threading.Lock(),standard_reader=reader)
        assert result['state']==expected and result['standard_algorithm']=='ALGO07'
        reader.state='complete'


def test_automatic_glrt_worker_budget_is_explicit_and_bounded(monkeypatch,tmp_path):
    import threading
    import pytest
    import leo.processing.fast_scan as processing
    from leo.cli.fast_scan import process_automatic
    from leo.storage.fast_scan import FastScanStore
    store=FastScanStore(tmp_path/'bulk');calls=[]
    def process(recording,**kwargs):
        calls.append(kwargs)
        return dict(run_id='run',session_id='session',window_count=1,counts={})
    monkeypatch.setattr(processing,'process_recording',process)
    class Reader:
        def detail(self,run_id):return dict(state='pending')
    arguments=dict(store=store,database_url='unused',standard_command=[],
                   glrt_lock=threading.Lock(),standard_reader=Reader(),standard_mode='algo07')
    for budget in (0,33,True,1.5):
        with pytest.raises(ValueError,match='1..32'):
            process_automatic(tmp_path/'recording',glrt_workers=budget,**arguments)
    assert not calls
    process_automatic(tmp_path/'recording',glrt_workers=16,**arguments)
    assert calls[0]['workers']==16 and calls[0]['export_tracking_input'] is True


@pytest.mark.parametrize("decision", ["complete", "withheld"])
def test_new_recording_uses_algo08_release(monkeypatch, tmp_path, decision):
    from threading import Lock
    from subprocess import CompletedProcess
    from leo.cli import fast_scan
    from leo.storage.fast_scan import FastScanStore

    store = FastScanStore(tmp_path)
    def worker(command, **kwargs):
        assert command == ["release/run", "--recording", str(tmp_path/"scan"), "--bulk-root", str(tmp_path)]
        assert store.automatic_status("scan")["standard_algorithm"] == "ALGO08"
        return CompletedProcess(command, 0, json.dumps(dict(decision=decision, run_id="algo08-example",
                                session_id="fast-source", terminal_sha256="sha256:terminal")), "")
    monkeypatch.setattr(fast_scan.subprocess, "run", worker)
    result = fast_scan.process_automatic(tmp_path/"scan", store=store, database_url="", standard_command=[],
                                         glrt_lock=Lock(), algo08_command=["release/run"])
    assert (result["state"], result["decision"]) == ("complete", decision)
