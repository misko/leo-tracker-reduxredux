"""Archive adapter rejects silent loss and mismatched capture authority."""
import importlib.util
import json
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest

SPEC = importlib.util.spec_from_file_location('projection_archive',
    Path(__file__).resolve().parents[3]/'tools/project_native_glrt_archive.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def archive(tmp_path, rows):
    root = tmp_path/'archive';root.mkdir()
    event = {'visit_index':0,'valid_start_counter':0,'valid_end_counter_exclusive':300000,
             'target':{'channel':1,'edge':'lower','rf_center_hz':11200000000},'actual_if_offset_hz':0}
    manifest = {'receipt':{'events':[event],'plan':{'geometry':{'sample_rate_hz':2500000,'receiver_ids':[0,1]}}},
                'timing':{'session_start_device_sample_counter':0,'first_sample_estimate_utc_ns':1}}
    docs = {'completion.json':{'status':'PASS'},'capture-manifest.json':manifest,
            'inventory.json':[{'event':event}]}
    for name,value in docs.items(): (root/name).write_text(json.dumps(value))
    call = {'result':{'sequence':0,'rate_hz':2500000,'dwell_ms':120,'stride_ms':120,'rows':rows}}
    (root/'batch-000000.jsonl').write_text(json.dumps(call)+'\n')
    return root,canonical_digest(manifest)


def row(rx):
    return {'receiver_id':rx,'probe_index':0,'probe_start_ms':0,'candidates':[]}


def test_missing_receiver_is_not_empty_detection(tmp_path):
    root,digest = archive(tmp_path,[row(0)])
    with pytest.raises(ValueError,match='missing detector'): MODULE.project(root,tmp_path/'out',digest)


def test_capture_digest_checked(tmp_path):
    root,_ = archive(tmp_path,[row(0),row(1)])
    with pytest.raises(ValueError,match='manifest digest'): MODULE.project(root,tmp_path/'out','wrong')


def test_valid_empty_detection_retains_complete_visit(tmp_path):
    root,digest = archive(tmp_path,[row(0),row(1)])
    receipt = MODULE.project(root,tmp_path/'out',digest)
    assert receipt['observations'] == 0 and receipt['visits'] == 1
