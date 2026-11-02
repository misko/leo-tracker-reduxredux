"""Public ALGO06 export and ALGO07 job lifecycle remain bound to original bytes."""

import json

import pytest

from leo.contracts.fast_graph_position_v5 import MODEL_VERSION as V5
from leo.contracts.fast_graph_position_v6 import MODEL_VERSION
from leo.storage.fast_graph_position import sha
from leo.storage.fast_graph_position_v5_export import FastGraphPositionStoreV5Export
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6


def export_store(tmp_path, monkeypatch):
    source = tmp_path / "source-terminal.json"
    source.write_text('{"unchanged": true}\n')
    old = dict(state="complete", session_id="scan", incumbent={"source": "ALGO05"})
    receipt = dict(path=str(source), sha256=sha(source))

    class Previous:
        def export_recovery(self, job, destination):
            destination.mkdir()
            member = destination / "incumbent-terminal.json"
            member.write_text('{"source":"ALGO05"}')
            result = dict(incumbent=old["incumbent"], files={member.name: sha(member)})
            (destination / "descriptor.json").write_text(json.dumps(result))
            return result

    store = FastGraphPositionStoreV5Export(tmp_path / "bulk", incumbent=Previous())
    monkeypatch.setattr(store, "status", lambda _: dict(state="complete"))
    monkeypatch.setattr(store, "terminal", lambda _: (old, receipt))
    return store, source


def test_export_composes_public_source_and_preserves_terminal_bytes(tmp_path, monkeypatch):
    store, source = export_store(tmp_path, monkeypatch)
    job = dict(job_id="job", input_sha256="sha256:test", source_job={"job_id": "old"})
    before = sha(source)
    destination = tmp_path / "export"
    descriptor = store.export_recovery(job, destination)
    assert descriptor["model_version"] == V5
    assert descriptor["incumbent_receipt"]["sha256"] == before == sha(source)
    assert (destination / "algo06-terminal.json").read_bytes() == source.read_bytes()
    for name, expected in descriptor["files"].items():
        assert sha(destination / name) == expected
    assert (destination / "source-export/descriptor.json").is_file()


def test_export_detects_terminal_mutation_during_source_export(tmp_path, monkeypatch):
    store, source = export_store(tmp_path, monkeypatch)
    export = store.incumbent.export_recovery

    def mutate(job, destination):
        result = export(job, destination)
        source.write_text("changed")
        return result

    monkeypatch.setattr(store.incumbent, "export_recovery", mutate)
    with pytest.raises(ValueError, match="changed while exporting"):
        store.export_recovery(
            dict(job_id="job", source_job={}, input_sha256="sha"), tmp_path / "export"
        )


@pytest.mark.parametrize("cutoff", [None, 0, -1, True, 1.5])
def test_export_completion_cutoff_is_explicit(tmp_path, cutoff):
    with pytest.raises(ValueError, match="cutoff"):
        list(
            FastGraphPositionStoreV5Export(tmp_path).completed_inputs(
                minimum_completed_utc_ns=cutoff
            )
        )


def test_v6_job_binds_public_incumbent_and_detects_change(tmp_path):
    class Source:
        receipt = {"sha256": "sha256:first"}

        def terminal(self, job):
            return dict(state="complete", session_id="scan"), self.receipt

    source = Source()
    store = FastGraphPositionStoreV6(tmp_path, incumbent=source)
    old = dict(
        job_id="old",
        model_version=V5,
        run_id="run",
        input_path="input",
        input_sha256="sha256:input",
        session_id="scan",
        source_job={},
        incumbent_terminal_sha256="sha256:previous",
    )
    job = store.job(old)
    assert job["model_version"] == MODEL_VERSION
    assert job["source_job"] == old
    store.verify_input(job)
    source.receipt = {"sha256": "sha256:changed"}
    with pytest.raises(ValueError, match="incumbent changed"):
        store.verify_input(job)


def test_v6_owner_is_exclusive_and_status_persists(tmp_path):
    store = FastGraphPositionStoreV6(tmp_path, incumbent=object())
    with store.owner("job") as first, store.owner("job") as second:
        assert first is True and second is False
    store.update({"job_id": "job"}, state="complete")
    assert store.status("job")["state"] == "complete"


def test_v6_lookup_uses_validated_public_terminal(tmp_path, monkeypatch):
    store = FastGraphPositionStoreV6(tmp_path, incumbent=object())
    store.update(dict(job_id="job", model_version=MODEL_VERSION, run_id="run"), state="complete")
    expected = dict(state="complete", position={"latitude_deg": 1, "longitude_deg": 2})
    monkeypatch.setattr(store, "terminal", lambda _: (expected, {}))
    assert store.completed_run("run") == expected
    monkeypatch.setattr(
        store, "terminal", lambda _: (_ for _ in ()).throw(ValueError("invalid proof"))
    )
    assert store.completed_run("run") is None


def test_plot_port_binds_owned_native_evidence_and_rejects_path_escape(tmp_path,monkeypatch):
    store=FastGraphPositionStoreV6(tmp_path,incumbent=object());job=dict(job_id='job')
    workspace=store.path('job')/'output/recovery';native=workspace/'native'
    native.mkdir(parents=True);(workspace/'inputs').mkdir()
    (native/'observations.json').write_text('[]');(native/'tracks.json').write_text('[]')
    context=workspace/'inputs/SCAN.json';context.write_text(json.dumps(dict(native_path=str(native))))
    monkeypatch.setattr(store,'terminal',lambda _: (dict(state='complete'),dict(sha256='sealed')))
    result=store.plot_evidence(job)
    assert result['observations']==[] and result['tracks']==[]
    assert result['observation_sha256']==sha(native/'observations.json')
    context.write_text(json.dumps(dict(native_path=str(tmp_path))))
    from leo.storage.errors import PathConfinementError
    with pytest.raises(PathConfinementError):store.plot_evidence(job)
