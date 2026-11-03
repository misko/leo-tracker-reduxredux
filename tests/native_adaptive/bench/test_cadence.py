"""Real child-process cadence, dependency, overload and failure tests."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    path=tmp_path_factory.mktemp('cadence')/'cadence'
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread',
                    str(ROOT/'native/adaptive/bench/cadence.cpp'),'-o',str(path)],
                   check=True,capture_output=True,text=True,
                   env={**os.environ,'TMPDIR':'/var/tmp'},timeout=60)
    return path


def fixture(tmp_path,count=3,detector_ms=450,downstream_ms=60,fail=False):
    child=tmp_path/'child.py'
    child.write_text('''import pathlib,sys,time
kind,product,delay,fail=sys.argv[1:5]
if kind=='detector':
    assert sys.argv[5]=='--start-monotonic-ns'
    origin=int(sys.argv[6]);now=time.monotonic_ns()
    if now>=origin:sys.exit(7)
    time.sleep((origin-now)/1e9)
    if fail=='yes':sys.exit(9)
    time.sleep(float(delay)/1000)
    pathlib.Path(product).write_text(str(origin))
else:
    assert pathlib.Path(product).is_file()
    time.sleep(float(delay)/1000)
print('done')
''')
    rows=[]
    for i in range(count):
        for kind,delay in [('detector',detector_ms),('downstream',downstream_ms)]:
            args=[sys.executable,str(child),kind,str(tmp_path/f'product-{i}'),str(delay),
                  'yes' if fail and i==0 else 'no']
            rows.append('\t'.join([kind,str(i),str(tmp_path/f'{kind}-{i}'),*args]))
    plan=tmp_path/'plan.tsv';plan.write_text('\n'.join(rows)+'\n');return plan


def run(binary,plan,period=600,lead=400):
    return subprocess.run([str(binary),str(plan),str(period),str(lead)],
                          capture_output=True,text=True,timeout=8)


def test_fixed_cadence_and_only_completed_products(binary,tmp_path):
    result=run(binary,fixture(tmp_path))
    assert result.returncode==0,result.stderr
    rows=[json.loads(x) for x in result.stdout.splitlines()]
    origins=[x['scan_origin_ns'] for x in rows if x['kind']=='launch' and x['detector']]
    assert [b-a for a,b in zip(origins,origins[1:])]==[600_000_000]*2
    for i in range(3):
        done=next(x for x in rows if x['kind']=='finish' and x['detector'] and x['scan']==i)
        start=next(x for x in rows if x['kind']=='launch' and not x['detector'] and x['scan']==i)
        assert start['monotonic_ns']>=done['monotonic_ns']
    assert rows[-1]['completed_scans']==3 and rows[-1]['pending_high_water']<=1
    assert rows[-1]['detector_process_high_water']==2
    assert rows[-1]['sampled_peak_process_tree_rss_kib']>0
    again=run(binary,tmp_path/'plan.tsv')
    assert again.returncode==2 and 'output already exists' in again.stderr


def test_downstream_overload_is_failure_not_schedule_rebase(binary,tmp_path):
    result=run(binary,fixture(tmp_path,count=4,detector_ms=20,downstream_ms=1000))
    assert result.returncode==2 and 'backlog capacity exceeded' in result.stderr
    assert '"success":true' not in result.stdout
    rows=[json.loads(x) for x in result.stdout.splitlines()]
    for row in rows:
        if row['kind']=='launch':
            with pytest.raises(ProcessLookupError):os.kill(row['pid'],0)


def test_failed_detector_never_releases_downstream(binary,tmp_path):
    result=run(binary,fixture(tmp_path,fail=True))
    assert result.returncode==2 and 'child failed' in result.stderr
    rows=[json.loads(x) for x in result.stdout.splitlines()]
    assert not any(x['kind']=='launch' and not x['detector'] for x in rows)


def test_plan_requires_complete_bounded_jobs(binary,tmp_path):
    plan=tmp_path/'plan';plan.write_text('detector\t0\t'+str(tmp_path/'out')+'\t/bin/true\n')
    result=run(binary,plan)
    assert result.returncode==2 and 'missing scan job' in result.stderr


def test_configured_monitoring_interval(binary,tmp_path):
    plan=fixture(tmp_path,count=1,detector_ms=20)
    result=subprocess.run([str(binary),str(plan),'600','400','5000'],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    row=json.loads(result.stdout.splitlines()[0])
    assert row['memory_sample_ms']==5000 and row['period_ns']==600_000_000


def test_sampler_calibration_is_bounded(binary):
    result=subprocess.run([str(binary),'--sample-cost','3'],capture_output=True,text=True,timeout=5,check=True)
    row=json.loads(result.stdout)
    assert row['samples']==3 and row['wall_ns']>0 and row['peak_rss_kib']>0
    result=subprocess.run([str(binary),'--sample-cost','1001'],capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and 'invalid sampler repetition count' in result.stderr


def test_process_stat_parser_matches_kernel_and_rejects_malformed(tmp_path):
    binary=tmp_path/'stat-test'
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-I'+str(ROOT/'native/adaptive/bench'),str(ROOT/'tests/native_adaptive/bench/test_process_stat.cpp'),
                    '-o',str(binary)],check=True,capture_output=True,text=True,
                   env={**os.environ,'TMPDIR':'/var/tmp'},timeout=30)
    subprocess.run([str(binary)],check=True,timeout=5)
