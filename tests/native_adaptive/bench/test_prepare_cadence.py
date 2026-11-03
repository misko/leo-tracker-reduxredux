import copy
import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_arm_cadence import prepare


def base():
    return {'payloads':dict.fromkeys(['/d','/script','/o','/g','/seed','/position'],'a'*64),
            'jobs':{'detector':{'argv':['/d','--observations','/old-o','--graph','/old-g']},
                    'search':{'argv':['/script']}},
            'chain':{'output_directory':'/mnt/glrtbench/old/results','stages':[
                {'name':'seed','argv':['/seed','/o'],'timeout_s':90},
                {'name':'search','argv':['/position','/o','/g','/mnt/glrtbench/old/results/seed.stdout'],'timeout_s':360}]},
            'absolute_score_tolerance_hz':1e-9}


def test_every_scan_consumes_its_own_products_and_pins_scripts():
    original=base();saved=copy.deepcopy(original)
    files,p=prepare(original,'/mnt/glrtbench/new',3,'b'*64,'c'*64)
    assert original==saved
    for i in range(3):
        text=files[f'scan-{i}/chain.sh']
        assert f'/scan-{i}/observations.tsv' in text and f'/scan-{i}/graph.tsv' in text
        assert '/old/' not in text and ' /o ' not in text
        assert p['payloads'][f'/mnt/glrtbench/new/scan-{i}/chain.sh']==hashlib.sha256(text.encode()).hexdigest()
    assert len(files['plan.tsv'].splitlines())==6
    assert '/o' not in p['payloads'] and '/g' not in p['payloads']


@pytest.mark.parametrize('remote,count',[('/tmp/x',3),('/mnt/glrtbench/../x',3),('/mnt/glrtbench/x',5)])
def test_invalid_scope_rejected(remote,count):
    with pytest.raises(ValueError):prepare(base(),remote,count,'b'*64,'c'*64)


def test_monitoring_interval_is_explicit_without_changing_scan_period():
    _,p=prepare(base(),'/mnt/glrtbench/new',3,'b'*64,'c'*64,5000)
    assert p['period_ms']==300000 and p['memory_sample_ms']==5000
    assert p['controller_argv'][-1]=='5000'
    with pytest.raises(ValueError):prepare(base(),'/mnt/glrtbench/new',3,'b'*64,'c'*64,0)
