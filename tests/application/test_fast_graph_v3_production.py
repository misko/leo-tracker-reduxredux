"""ALGO04 production ports, exact ALGO03 fallback and bounded watcher checks."""

import copy
import json
import time
from argparse import Namespace
from contextlib import contextmanager

import pytest
from algo03_production_worker import envelope

from leo.application.automatic_fast_graph_v3 import process
from leo.cli import fast_graph_position_v3 as cli
from leo.contracts.fast_graph_position_v3 import MODEL_VERSION
from leo.storage import fast_graph_position_v2 as storage_v2
from leo.storage.fast_graph_position_v3 import FastGraphPositionStoreV3
from leo.storage.fast_scan import immutable_json
from tests.application.test_fast_graph_v2_production import setup as setup_v2


def setup(tmp_path):
    baseline, incumbent, source, original = setup_v2(tmp_path)
    cutoff = time.time_ns()
    source_job = incumbent.job(source)
    terminal = envelope(original, dict(failure="No RF addition"), recovery_seconds=2.0)
    immutable_json(incumbent.path(source_job["job_id"]) / "output/terminal.json", terminal)
    incumbent.update(source_job, state="complete")
    store = FastGraphPositionStoreV3(tmp_path, incumbent=incumbent)
    return baseline, incumbent, source_job, terminal, store, cutoff


def fallback(incumbent):
    return dict(
        schema_version=3,
        kind=incumbent["kind"],
        model_version=MODEL_VERSION,
        input_sha256=incumbent["input_sha256"],
        session_id=incumbent["session_id"],
        state="complete",
        incumbent=copy.deepcopy(incumbent),
        candidate=None,
        decision="ALGO03_fallback",
        position=copy.deepcopy(incumbent["position"]),
        incumbent_seconds=incumbent["total_seconds"],
        numerical_seconds=3.0,
        total_seconds=incumbent["total_seconds"] + 3.0,
        reference_usage="none",
        future_TLE_used=False,
        matched_c_inputs=True,
        selected_arm="fitted_c",
    )


def recovery_tree(incumbent, job):
    root = incumbent.path(job["job_id"]) / "output/recovery"
    (root / "snapshot").mkdir(parents=True)
    (root / "snapshot/bank.npz").write_bytes(b"immutable numerical bank")
    (root / "decision.json").write_text(json.dumps({"original_path": str(root), "selected": None}))
    return root


def test_only_newly_completed_v2_jobs_are_discovered_not_old_baseline_cutoffs(tmp_path):
    _, incumbent, source, _, store, cutoff = setup(tmp_path)
    assert list(incumbent.inputs(minimum_completed_utc_ns=cutoff)) == []
    jobs = list(store.inputs(minimum_completed_utc_ns=cutoff))
    assert len(jobs) == 1 and jobs[0]["source_job"]["job_id"] == source["job_id"]
    assert jobs[0]["job_id"] != source["job_id"]
    assert jobs[0]["model_version"] == MODEL_VERSION
    assert store.namespace != incumbent.namespace
    assert list(store.inputs(minimum_completed_utc_ns=time.time_ns() + 1_000_000)) == []
    with pytest.raises(ValueError):
        list(store.inputs(minimum_completed_utc_ns=0))


def test_export_recovery_copies_exact_private_bytes_without_rewriting_source_references(tmp_path):
    _, incumbent, source, terminal, _, _ = setup(tmp_path)
    original = recovery_tree(incumbent, source)
    before = (original / "decision.json").read_bytes()
    destination = tmp_path / "private-export"
    descriptor = incumbent.export_recovery(source, destination)
    assert descriptor["incumbent"] == terminal
    assert descriptor["source_recovery_root"] == str(original)
    assert (destination / "recovery/decision.json").read_bytes() == before
    assert (destination / "recovery/decision.json").stat().st_ino != (
        original / "decision.json"
    ).stat().st_ino
    assert destination.stat().st_mode & 0o777 == 0o700
    assert (destination / "recovery/decision.json").stat().st_mode & 0o777 == 0o600
    for name, expected in descriptor["files"].items():
        assert storage_v2.sha(destination / name) == expected
    assert json.loads((destination / "incumbent-terminal.json").read_text()) == terminal
    (destination / "recovery/decision.json").write_text("local relocated copy")
    assert (original / "decision.json").read_bytes() == before


@pytest.mark.parametrize("link_kind", ["file", "directory", "recovery_root"])
def test_export_recovery_rejects_symbolic_links(tmp_path, link_kind):
    _, incumbent, source, _, _, _ = setup(tmp_path)
    root = recovery_tree(incumbent, source)
    if link_kind == "file":
        (root / "linked.json").symlink_to(root / "decision.json")
    elif link_kind == "directory":
        (root / "linked-directory").symlink_to(root / "snapshot", target_is_directory=True)
    else:
        real = root.with_name("real-recovery")
        root.rename(real)
        root.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic links"):
        incumbent.export_recovery(source, tmp_path / "rejected-export")


def test_export_recovery_detects_source_change_during_copy(tmp_path, monkeypatch):
    _, incumbent, source, _, _, _ = setup(tmp_path)
    root = recovery_tree(incumbent, source)
    original_copy = storage_v2.shutil.copyfile

    def racing_copy(src, dest):
        result = original_copy(src, dest)
        if src == root / "decision.json":
            src.write_text("changed while exporting")
        return result

    monkeypatch.setattr(storage_v2.shutil, "copyfile", racing_copy)
    with pytest.raises(ValueError, match="changed while exporting"):
        incumbent.export_recovery(source, tmp_path / "rejected-export")


def test_export_cannot_write_inside_production_namespace(tmp_path):
    _, incumbent, source, _, _, _ = setup(tmp_path)
    recovery_tree(incumbent, source)
    with pytest.raises(ValueError, match="production source namespace"):
        incumbent.export_recovery(source, incumbent.namespace / "forbidden-export")


def test_export_rejects_qnap_destination_without_accessing_qnap(tmp_path):
    _, incumbent, source, _, _, _ = setup(tmp_path)
    recovery_tree(incumbent, source)
    with pytest.raises(ValueError, match="read-only"):
        incumbent.export_recovery(source, "/mnt/qnap01/never-created-algo04-export")


def test_corrupt_completed_status_is_logged_without_starving_later_jobs(tmp_path, caplog):
    _, incumbent, source, _, store, _ = setup(tmp_path)
    bad = incumbent.namespace / "jobs/000-bad/status.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("corrupt status")
    assert [j["source_job"]["job_id"] for j in store.inputs(minimum_completed_utc_ns=1)] == [
        source["job_id"]
    ]
    assert "Rejected completed ALGO03 job 000-bad" in caplog.text


def test_v3_application_passes_source_v2_job_and_preserves_incumbent_bytes(tmp_path):
    _, incumbent, source, terminal, store, _ = setup(tmp_path)
    job = store.job(source)
    original_path = incumbent.path(source["job_id"]) / "output/terminal.json"
    before = original_path.read_bytes()
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        output = store.path(job["job_id"]) / "output"
        output.mkdir()
        immutable_json(output / "terminal.json", fallback(terminal))
        return 0

    result = process(job, store=store, command=["worker"], maximum_seconds=30, runner=runner)
    assert result["state"] == "complete" and result["result"]["decision"] == "ALGO03_fallback"
    assert calls[0][0][calls[0][0].index("--job") + 1] == source["job_id"]
    assert calls[0][1] == 45
    assert original_path.read_bytes() == before
    store.update(job, state="running")
    assert process(job, store=store, command=["worker"], runner=runner)["state"] == "complete"
    assert len(calls) == 1


def test_changed_incumbent_cannot_launch_or_publish(tmp_path):
    _, incumbent, source, _, store, _ = setup(tmp_path)
    job = store.job(source)
    path = incumbent.path(source["job_id"]) / "output/terminal.json"
    changed = json.loads(path.read_text())
    changed["recovery_seconds"] += 1
    changed["total_seconds"] += 1
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="incumbent changed"):
        process(
            job,
            store=store,
            command=["worker"],
            runner=lambda *args, **kwargs: pytest.fail("Must not launch"),
        )


def test_interrupted_v3_job_has_no_hidden_automatic_retry(tmp_path):
    _, _, source, _, store, _ = setup(tmp_path)
    job = store.job(source)
    store.update(job, state="running")
    result = process(
        job,
        store=store,
        command=["worker"],
        runner=lambda *args, **kwargs: pytest.fail("Must not retry"),
    )
    assert result["state"] == "failed" and "no automatic retry" in result["failure"]


def test_v3_consumes_only_public_incumbent_ports(tmp_path):
    _, _, source, terminal, _, _ = setup(tmp_path)

    class PublicPort:
        @property
        def namespace(self):
            pytest.fail("V3 must not inspect another component's namespace")

        def terminal(self, job):
            assert job["job_id"] == source["job_id"]
            return terminal, {"sha256": "sha256:incumbent"}

        def completed_inputs(self, *, minimum_completed_utc_ns):
            assert minimum_completed_utc_ns == 123
            yield source

    store = FastGraphPositionStoreV3(tmp_path, incumbent=PublicPort())
    job = next(store.inputs(minimum_completed_utc_ns=123))
    store.verify_input(job)


def test_once_watcher_selects_only_explicit_v2_canary_and_single_worker(tmp_path, monkeypatch):
    calls = []

    class Store:
        @contextmanager
        def owner(self, name):
            assert name == "watcher"
            yield True

        def inputs(self, *, minimum_completed_utc_ns):
            assert minimum_completed_utc_ns == 123
            for name in ("unselected", "canary"):
                yield {"job_id": "v3-" + name, "source_job": {"job_id": name}}

        def status(self, identifier):
            return None

    def fake_process(job, **kwargs):
        calls.append(job["source_job"]["job_id"])
        assert kwargs["maximum_seconds"] == 30
        return dict(job_id=job["job_id"], state="complete")

    monkeypatch.setattr(cli, "FastGraphPositionStoreV3", lambda root: Store())
    monkeypatch.setattr(cli, "process", fake_process)
    cli.watch(
        Namespace(
            bulk_root=tmp_path,
            minimum_completed_utc_ns=123,
            source_job="canary",
            once=True,
            maximum_seconds=30,
        )
    )
    assert calls == ["canary"]
