import copy
import importlib.util
from pathlib import Path
import pytest
import threading

spec=importlib.util.spec_from_file_location('arm_overlap',Path(__file__).resolve().parents[3]/'tools/run_arm_overlap.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def protocol():
    return {'jobs':{name:{'argv':['/mnt/glrtbench/tool','input'],'nice':0,'timeout_s':420}
                    for name in ['detector','search']},
            'payloads':{'/mnt/glrtbench/tool':'a'*64},
            'downloads':{name:'/mnt/glrtbench/'+name for name in ['observations','graph']}}


def test_valid_overlap():module.validate(protocol())


def test_both_workloads_start_and_failed_exit_does_not_discard_other_result():
    barrier=threading.Barrier(2,timeout=5)
    def run(name):
        barrier.wait()
        return {'exit_code':3 if name=='detector' else 0}
    result=module.concurrent_results(['detector','search'],run)
    assert result=={'detector':{'exit_code':3},'search':{'exit_code':0}}


@pytest.mark.parametrize('key,value',[('timeout_s',601),('timeout_s',True),('nice',-1),('nice',20),
                                    ('argv',[]),('argv',['/bin/unpinned']),('cpu_mask',0),
                                    ('cpu_mask',4),('cpu_mask',True)])
def test_invalid_workload(key,value):
    p=protocol();p['jobs']['search'][key]=value
    with pytest.raises(ValueError):module.validate(p)


def test_required_jobs_and_products():
    for key in ['jobs','downloads']:
        p=copy.deepcopy(protocol());p[key].pop(next(iter(p[key])))
        with pytest.raises(ValueError):module.validate(p)
    p=protocol();p['downloads']['graph']='/mnt/glrtbench/../elsewhere'
    with pytest.raises(ValueError):module.validate(p)


def test_affinity_is_explicit_and_preserves_argument_boundaries():
    p=protocol();job=p['jobs']['detector'];job['argv'].append('argument with spaces')
    baseline=module.workload_argv(job)
    assert 'taskset' not in baseline and baseline[-1]=='argument with spaces'
    job['affinity_launcher']='/mnt/glrtbench/affinity'
    p['payloads'][job['affinity_launcher']]='b'*64
    for mask in [1,2,3]:
        job['cpu_mask']=mask;module.validate(p)
        actual=module.workload_argv(job)
        assert actual[5:7]==[job['affinity_launcher'],str(mask)]
        assert actual[7:]==job['argv'] and actual[:5]==baseline[:5]


def test_unpinned_affinity_launcher_rejected():
    p=protocol();p['jobs']['detector']['cpu_mask']=1
    with pytest.raises(ValueError,match='launcher must be pinned'):module.validate(p)
