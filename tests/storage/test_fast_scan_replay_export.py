import hashlib
import json

import pytest

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore, immutable_json


def native(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    store = FastScanStore(root)
    inventory = dict(kind='fast-scan-source', recording_name='scan',
                     segments=[dict(path='/unused')])
    source = dict(session_id='session', input_manifest_sha256=canonical_digest(inventory))
    immutable_json(root/'fast-scan-inputs/session.json', inventory)
    store.publish('run', dict(run_id='run', session_id='session'))
    store.publish_tracking_input('run', dict(source=source))
    return store


def test_export_preserves_original_input_bytes_and_has_no_prior_results(tmp_path):
    source = native(tmp_path)
    target = tmp_path/'private'
    receipt = source.export_replay_inputs('run', target)
    assert receipt['raw_iq_reverified'] is False
    assert receipt['numerical_inference_run'] is False
    assert len(receipt['files']) == 3
    cloned = FastScanStore(target)
    assert (cloned.tracking_input_path('run').read_bytes() ==
            source.tracking_input_path('run').read_bytes())
    for row in receipt['files']:
        assert hashlib.sha256((target/row['path']).read_bytes()).hexdigest() == row['sha256']


def test_corrupt_inventory_rejected_before_creating_destination(tmp_path):
    source = native(tmp_path)
    (source.root/'fast-scan-inputs/session.json').write_text('{}')
    with pytest.raises(ValueError, match='inventory changed'):
        source.export_replay_inputs('run', tmp_path/'private')
    assert not (tmp_path/'private').exists()


def test_cross_session_report_rejected(tmp_path):
    source = native(tmp_path)
    (source.root/'fast-scan-reports/run.json').write_text(json.dumps(dict(run_id='run',session_id='wrong')))
    with pytest.raises(ValueError, match='disagree'):
        source.export_replay_inputs('run', tmp_path/'private')


def test_never_overwrite_source_or_qnap(tmp_path):
    source = native(tmp_path)
    for target in [source.root, tmp_path, '/mnt/qnap01/forbidden']:
        with pytest.raises(ValueError, match='local replay store'):
            source.export_replay_inputs('run', target)
