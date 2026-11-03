"""Real executor/IO pacing tests with a deterministic slow detector port."""
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    work=tmp_path_factory.mktemp('recorded-pacing')
    stub=work/'detector.cpp'
    stub.write_text('''
extern "C" {
#include "native_glrt.h"
}
#include <thread>
#include <chrono>
struct leo_native_glrt {};
extern "C" int leo_native_glrt_create(leo_native_glrt** p,uint32_t,
 const leo_native_glrt_complex*,const leo_native_glrt_complex*,size_t){*p=new leo_native_glrt;return 0;}
extern "C" int leo_native_glrt_destroy(leo_native_glrt* p){delete p;return 0;}
extern "C" int leo_native_glrt_analyze(leo_native_glrt*,const int16_t* iq,size_t,
 uint32_t,uint32_t,leo_native_glrt_result* r){
 std::this_thread::sleep_for(std::chrono::milliseconds(80));r->row_count=2;
 r->rows[0].receiver_id=0;r->rows[1].receiver_id=1;r->rows[0].candidate_count=1;
 auto& c=r->rows[0].candidates[0];c.epoch=722;c.tracking_cfo_hz=-100;
 c.acquired_cfo_hz=iq[200000];
 c.exact_score=.4;c.control_score=.1;c.margin=.3;c.glrt_complete=1;return 0;}
''')
    out=work/'paced'
    subprocess.run(['g++','-std=c++17','-O1','-pthread',
        '-I'+str(ROOT/'native/adaptive/detector'),
        str(ROOT/'native/adaptive/bench/recorded_paced.cpp'),
        str(ROOT/'native/adaptive/runtime/runtime.cpp'),
        str(ROOT/'native/adaptive/runtime/projection.cpp'),str(stub),'-o',str(out)],
        check=True,capture_output=True,text=True,env={**os.environ,'TMPDIR':'/var/tmp'},timeout=60)
    return out


def run(binary,tmp_path,offsets,prefix=False,reuse=False,capacity=1):
    template=tmp_path/'template';template.write_bytes(bytes(3333*16))
    iq=tmp_path/'iq';iq.write_bytes(bytes(2400000))
    manifest=tmp_path/'manifest.tsv'
    manifest.write_text(''.join(f'{i}\t{offset}\t{template}\t{template}\t{iq}\n'
                                for i,offset in enumerate(offsets)))
    return subprocess.run([str(binary),str(manifest),str(capacity)]+(['--probe-prefix'] if prefix else [])+
                          (['--reuse-iq'] if reuse else []),
                          capture_output=True,text=True,timeout=5)


def test_original_schedule_drains_without_loss(binary,tmp_path):
    result=run(binary,tmp_path,[0,150000000,300000000])
    assert result.returncode==0,result.stderr
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    assert rows[-1]['completed']==3 and rows[-1]['rejected']==0
    assert all(r['accepted'] and r['service_ms']>=70 for r in rows[:-1])


def test_overload_is_visible_and_iq_queue_bounded(binary,tmp_path):
    result=run(binary,tmp_path,[i*1000000 for i in range(10)])
    assert result.returncode==3,result.stderr
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    summary=rows[-1]
    assert summary['queue_high_water']==1
    assert summary['rejected']>0
    assert summary['completed']+summary['rejected']==10
    assert sum(not r['accepted'] for r in rows[:-1])==summary['rejected']


def test_nonmonotonic_schedule_rejected(binary,tmp_path):
    result=run(binary,tmp_path,[0,0])
    assert result.returncode==2
    assert 'invalid arrival schedule' in result.stderr


@pytest.mark.parametrize('capacity,count',[(32,24),(48,40)])
def test_larger_bounded_queue_absorbs_burst(binary,tmp_path,capacity,count):
    result=run(binary,tmp_path,[i*1000000 for i in range(count)],prefix=True,reuse=True,capacity=capacity)
    assert result.returncode==0,result.stderr
    summary=json.loads(result.stdout.splitlines()[-1])
    assert summary['completed']==count and summary['rejected']==0
    assert summary['queue_capacity']==capacity and capacity-16<summary['queue_high_water']<=capacity
    assert summary['iq_buffer_allocations']<=capacity+2


@pytest.mark.parametrize('capacity,count',[(32,40),(48,56)])
def test_larger_queue_still_rejects_overload(binary,tmp_path,capacity,count):
    result=run(binary,tmp_path,[i*1000000 for i in range(count)],prefix=True,reuse=True,capacity=capacity)
    assert result.returncode==3,result.stderr
    summary=json.loads(result.stdout.splitlines()[-1])
    assert summary['queue_high_water']==capacity and summary['rejected']>0
    assert summary['completed']+summary['rejected']==count
    assert summary['iq_buffer_allocations']<=capacity+2


@pytest.mark.parametrize('capacity',[0,49])
def test_queue_capacity_limits(binary,tmp_path,capacity):
    result=run(binary,tmp_path,[0],capacity=capacity)
    assert result.returncode==2 and 'queue capacity' in result.stderr


def test_external_origin_preserved_and_no_early_processing(binary,tmp_path):
    run(binary,tmp_path,[0])
    origin=time.clock_gettime_ns(time.CLOCK_MONOTONIC)+500_000_000
    result=subprocess.run([str(binary),str(tmp_path/'manifest.tsv'),'1',
        '--start-monotonic-ns',str(origin)],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    clock=json.loads(result.stderr.splitlines()[0])
    assert clock['external_origin'] and clock['origin_ns']==origin
    assert clock['ready_ns']<origin
    row=json.loads(result.stdout.splitlines()[0])
    assert row['producer_late_ms']>=0 and row['due_to_finish_ms']>=70
    assert time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=origin+70_000_000


def test_controller_clock_uses_linux_monotonic_epoch(binary):
    before=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    result=subprocess.run([str(binary),'--clock-now'],capture_output=True,text=True,
                          check=True,timeout=5)
    after=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    assert before<=int(result.stdout)<=after


@pytest.mark.parametrize('origin',['0','18446744073709551615'])
def test_external_origin_rejects_invalid_range(binary,tmp_path,origin):
    run(binary,tmp_path,[0])
    result=subprocess.run([str(binary),str(tmp_path/'manifest.tsv'),'1',
        '--start-monotonic-ns',origin],capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and 'invalid monotonic origin' in result.stderr
    assert not result.stdout


@pytest.mark.parametrize('offset,message',[
    (-1_000_000_000,'missed monotonic origin'),
    (120_000_000_000,'initialization lead limit')])
def test_external_origin_does_not_silently_rebase(binary,tmp_path,offset,message):
    run(binary,tmp_path,[0])
    origin=time.clock_gettime_ns(time.CLOCK_MONOTONIC)+offset
    result=subprocess.run([str(binary),str(tmp_path/'manifest.tsv'),'1',
        '--start-monotonic-ns',str(origin)],capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and message in result.stderr
    assert not result.stdout


def test_probe_prefix_mode_is_explicit_in_result(binary,tmp_path):
    result=run(binary,tmp_path,[0],prefix=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['probe_prefix_only']


def test_reuse_is_bounded_and_preserves_candidates(binary,tmp_path):
    control=run(binary,tmp_path,[0,150000000,300000000],prefix=True)
    reused=run(binary,tmp_path,[0,150000000,300000000],prefix=True,reuse=True)
    assert control.returncode==reused.returncode==0
    a=[json.loads(v) for v in control.stdout.splitlines()]
    b=[json.loads(v) for v in reused.stdout.splitlines()]
    assert [v['candidates'] for v in a[:-1]]==[v['candidates'] for v in b[:-1]]
    assert b[-1]['iq_reuse'] and b[-1]['iq_buffer_allocations']==1
    assert not a[-1]['iq_reuse'] and a[-1]['iq_buffer_allocations']==3
    for row in b[:-1]:
        assert all(row[k]>=0 for k in ['io_cpu_ms','detector_cpu_ms','projection_cpu_ms','service_cpu_ms'])
    overloaded=run(binary,tmp_path,[i*1000000 for i in range(10)],prefix=True,reuse=True)
    assert overloaded.returncode==3
    summary=json.loads(overloaded.stdout.splitlines()[-1])
    assert summary['iq_buffer_allocations']<=3 and summary['rejected']>0


@pytest.mark.parametrize('prefix',[False,True])
def test_reuse_overwrites_full_inputs_and_preserves_zero_prefix_tail(binary,tmp_path,prefix):
    run(binary,tmp_path,[0,150000000])
    first=tmp_path/'iq';second=tmp_path/'iq2'
    first.write_bytes(bytes(400000)+b'\x03\x00'*1000000)
    second.write_bytes(bytes(400000)+b'\x07\x00'*1000000)
    manifest=tmp_path/'manifest.tsv'
    lines=manifest.read_text().splitlines();fields=lines[1].split('\t');fields[-1]=str(second)
    manifest.write_text(lines[0]+'\n'+'\t'.join(fields)+'\n')
    result=subprocess.run([str(binary),str(manifest),'1','--reuse-iq']+
                          (['--probe-prefix'] if prefix else []),capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    rows=[json.loads(v) for v in result.stdout.splitlines()]
    assert [v['candidates'][0][4] for v in rows[:-1]]==([0,0] if prefix else [3,7])
    assert rows[-1]['iq_buffer_allocations']==1


def test_direct_projection_produces_checkpoint_and_separate_timing(binary,tmp_path):
    run(binary,tmp_path,[0])  # Build the explicit local fixture and arrival manifest.
    authority=tmp_path/'authority.tsv';output=tmp_path/'observations.tsv'
    graph=tmp_path/'graph.tsv'
    fields=[2500000,100,1000000000,1,0,100,0,0,1,0,11200000000,0,
            'sha256:'+'a'*64,'sha256:'+'b'*64,1]
    authority.write_text('\t'.join(map(str,fields))+'\n')
    result=subprocess.run([str(binary),str(tmp_path/'manifest.tsv'),'1','--probe-prefix',
        '--authority',str(authority),'--observations',str(output),'--graph',str(graph),'--session','test-scan'],
        capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    rows=output.read_text().splitlines();assert len(rows)==2
    assert rows[0].startswith('candidate_id\tsource_group_id\treceiver_id')
    assert float(rows[1].split('\t')[9])==-100
    support=graph.read_text().splitlines()
    assert support[0]=='META\ttest-scan\tsha256:'+'a'*64+'\t1000000000'
    assert support[2].split('\t')[:4]==[rows[1].split('\t')[i] for i in [0,6,7,8]]
    assert float(support[2].split('\t')[6])>0
    arrival=json.loads(result.stdout.splitlines()[0])
    assert arrival['detector_ms']>=70 and arrival['projection_ms']>0
    again=subprocess.run([str(binary),str(tmp_path/'manifest.tsv'),'1','--authority',str(authority),
        '--observations',str(output)],capture_output=True,text=True,timeout=5)
    assert again.returncode==2 and 'already exists' in again.stderr


def test_graph_requires_projection_and_session(binary,tmp_path):
    for flags in [ ['--graph',str(tmp_path/'graph')],
                   ['--graph',str(tmp_path/'graph'),'--session','scan'],
                   ['--authority','a','--observations','o','--graph','g','--session','bad session'],
                   ['--authority','a','--observations','same','--graph','same','--session','scan'] ]:
        result=subprocess.run([str(binary),'unused-manifest','1',*flags],
                              capture_output=True,text=True,timeout=5)
        assert result.returncode==2
        assert 'graph requires projection and a valid session identity' in result.stderr
