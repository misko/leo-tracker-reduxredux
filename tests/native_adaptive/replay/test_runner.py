"""Portable runner contract tests; fake executables never open a radio."""
import json
import sys
from pathlib import Path

import pytest

from leo.native_pipeline.recipes import glrt_stage, location_stage, tracker_stages
from leo.native_pipeline.runner import digest, run, validate_plan, write_json


def fixture(tmp_path, code='print(\'{"ok":true}\')'):
    script = tmp_path/'fake.py'
    script.write_text(code+'\n')
    plan = {'schema':'leo-native-replay/v1','execution':{'mode':'serial','workers':1},
        'inputs':{'python':{'path':sys.executable,'sha256':digest(sys.executable),'format':'executable'},
                  'script':{'path':str(script),'sha256':digest(script),'format':'executable'}},
        'stages':[{'id':'fake','kind':'diagnostic','executable':'python','argv':['@script'],
                   'format':'json-v1','timeout_s':2}]}
    path = tmp_path/'plan.json'
    write_json(path,plan)
    return path,plan


def test_receipt_and_no_overwrite(tmp_path):
    path,plan = fixture(tmp_path)
    result = run(path,tmp_path/'out')
    assert result['status'] == 'complete'
    assert result['stages'][0]['argv'][0] == sys.executable
    assert result['stages'][0]['output_sha256'] == digest(tmp_path/'out/fake.output')
    with pytest.raises(FileExistsError): run(path,tmp_path/'out')


def test_tampered_input_rejected_before_execution(tmp_path):
    path,_ = fixture(tmp_path)
    (tmp_path/'fake.py').write_text('raise RuntimeError()')
    with pytest.raises(ValueError,match='digest mismatch'): run(path,tmp_path/'out')
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('code', ['raise SystemExit(7)', 'print("invalid json")', 'print("NaN")', 'print("1e999")'])
def test_failure_never_published_as_complete(tmp_path,code):
    path,_ = fixture(tmp_path,code)
    with pytest.raises((RuntimeError,ValueError)): run(path,tmp_path/'out')
    assert json.loads((tmp_path/'out/receipt.json').read_text())['status'] == 'failed'


def test_timeout_recorded(tmp_path):
    import subprocess
    path,plan = fixture(tmp_path,'import time; time.sleep(10)')
    plan['stages'][0]['timeout_s'] = .05
    write_json(path,plan)
    with pytest.raises(subprocess.TimeoutExpired): run(path,tmp_path/'out')
    result = json.loads((tmp_path/'out/receipt.json').read_text())
    assert result['stages'][0]['status'] == 'timeout'


def test_dependency_order_and_worker_budget(tmp_path):
    _,plan = fixture(tmp_path)
    plan['stages'][0]['argv'] = ['@future']
    with pytest.raises(ValueError,match='forward'): validate_plan(plan)
    plan['execution']['workers'] = 2
    with pytest.raises(ValueError,match='serial'): validate_plan(plan)


def test_upstream_mutation_fails_run(tmp_path):
    path,plan = fixture(tmp_path,'import pathlib; pathlib.Path(__file__).write_text("changed"); print("{}")')
    with pytest.raises(ValueError,match='changed during'): run(path,tmp_path/'out')


def test_frozen_output_mismatch(tmp_path):
    path,plan = fixture(tmp_path)
    plan['stages'][0]['expected_sha256'] = '0'*64
    write_json(path,plan)
    with pytest.raises(ValueError,match='frozen expectation'): run(path,tmp_path/'out')


def test_recipes_keep_scientific_options_explicit():
    stages = tracker_stages('coarse-seeded','tracker','observations',seed_executable='seed')
    assert stages[0]['argv'][1:] == ['151','8','512','8','4','16']
    assert stages[1]['argv'][-4:] == ['--acceleration','250','--seeds','@coarse-seeds']
    assert glrt_stage('detector','iq','exact','control',rate_hz=2500000)['argv'][4:6] == ['--probe-stride-ms','120']
    assert location_stage('solver','fixture',workers=2)['argv'] == ['score','@fixture','2']
    with pytest.raises(ValueError): tracker_stages('unknown','t','o')


def test_iq_geometry_validated(tmp_path):
    path,plan = fixture(tmp_path)
    iq = tmp_path/'input.ci16'; iq.write_bytes(b'\0'*8)
    plan['inputs']['iq'] = {'path':str(iq),'sha256':digest(iq),'format':'iq-ci16-v1',
        'metadata':{'sample_rate_hz':2500000,'receivers':2,'sample_count':2,
                    'layout':'sample-receiver-iq','byte_order':'little',
                    'first_counter':0,'end_counter':2,'actual_rf_hz':11.2e9,
                    'time_authority':'sample-counter-anchor','first_sample_utc_ns':1,
                    'utc_uncertainty_ns':0}}
    write_json(path,plan)
    with pytest.raises(ValueError,match='byte count'): run(path,tmp_path/'out')


def test_secondary_output_is_validated_and_consumed(tmp_path):
    code = 'import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.mkdir(); (p/"data.json").write_text("{\\"n\\":42}"); print("{}")'
    path,plan = fixture(tmp_path,code)
    stage = plan['stages'][0]
    stage['argv'].append('@output-dir')
    stage['artifacts'] = [{'id':'data','path':'data.json','format':'json-v1'}]
    plan['stages'].append({'id':'consumer','kind':'diagnostic','executable':'python',
        'argv':['-c','import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text())','@data'],
        'format':'json-v1','timeout_s':2})
    write_json(path,plan)
    result = run(path,tmp_path/'out')
    assert result['status'] == 'complete'
    assert json.loads((tmp_path/'out/consumer.output').read_text()) == {'n':42}
    assert result['stages'][0]['artifacts'][0]['id'] == 'data'


def test_secondary_output_missing_fails(tmp_path):
    path,plan = fixture(tmp_path)
    plan['stages'][0]['artifacts'] = [{'id':'data','path':'data.json','format':'json-v1'}]
    write_json(path,plan)
    with pytest.raises(FileNotFoundError): run(path,tmp_path/'out')
    result = json.loads((tmp_path/'out/receipt.json').read_text())
    assert result['status'] == 'failed' and result['stages'][0]['status'] == 'failed'


def test_secondary_output_path_escape_rejected(tmp_path):
    _,plan = fixture(tmp_path)
    plan['stages'][0]['artifacts'] = [{'id':'data','path':'../data.json','format':'json-v1'}]
    with pytest.raises(ValueError,match='inside'): validate_plan(plan)
