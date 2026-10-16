import json

import pytest

from leo.cli.shared_fast_orbits import publish
from leo.contracts.digests import sha256_digest
from leo.contracts.fast_scan_orbits import PLOT_NAMES
from tests.storage.test_shared_fast_scan import source, terminal


def completed(tmp_path):
    _, store, job = source(tmp_path)
    folder = store.workspace(job['job_id']) / 'output' / 'stages'
    folder.mkdir(parents=True)
    stage = folder / 'source-selection.json'
    stage.write_text('{}')
    terminal(store, job, stage_receipts=[dict(path=str(stage), sha256=sha256_digest(stage.read_bytes()))])
    _, binding = store.terminal(job)
    store.update(job, state='complete', terminal=binding)
    return store, job, stage, binding


def test_evidence_checks_stage_bytes_and_terminal_binding(tmp_path):
    store, job, stage, _ = completed(tmp_path)
    assert store.plot_evidence(job['job_id'])[3] == {'source-selection': {}}
    stage.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='stage evidence changed'):
        store.plot_evidence(job['job_id'])


def test_idempotent_cli_publisher_verifies_existing_pngs_without_refitting(tmp_path):
    store, job, _, binding = completed(tmp_path)
    png = b'\x89PNG\r\n\x1a\nshared'
    output = store.orbit_store()
    output.publish_orbits(job['run_id'], dict.fromkeys(PLOT_NAMES, png),
                          {'terminal_sha256': binding['sha256']})
    result = publish(store, job['job_id'], tmp_path / 'no-tle-needed')
    assert len(result['artifacts']) == 4
    # Changing the terminal while retaining its old published binding fails before replay.
    path = store.output_path(job['job_id']) / 'terminal.json'
    value = json.loads(path.read_text())
    value['reason'] = 'changed'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='terminal changed'):
        publish(store, job['job_id'], tmp_path)
