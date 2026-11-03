import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    out=tmp_path_factory.mktemp('preparation-bench')/'bench'
    base=ROOT/'native/adaptive';pipeline=base/'pipeline'
    subprocess.run(['g++','-std=c++17','-O2','-fno-fast-math',
        *['-I'+str(base/n) for n in ['pipeline','tracking','location','runtime']],
        str(pipeline/'research/preparation_bench.cpp'),
        *[str(pipeline/n) for n in ['pipeline.cpp','track_input.cpp','selection.cpp']],
        '-o',str(out)],check=True,capture_output=True,text=True,
        env={**os.environ,'TMPDIR':'/var/tmp'},timeout=60)
    return out


def test_missing_input_is_explicit(binary,tmp_path):
    result=subprocess.run([str(binary),*[str(tmp_path/'absent')]*3],capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and 'missing input' in result.stderr


def test_measured_preparation_preserves_point_values(binary,tmp_path):
    base=1_800_000_000_000_000_000
    ids=['sha256:'+hashlib.sha256(f'point{i}'.encode()).hexdigest() for i in range(8)]
    sources=['sha256:'+hashlib.sha256(f'source{i}'.encode()).hexdigest() for i in range(8)]
    observations=['header'];graph=['META\tscan\tsha256:'+'a'*64+f'\t{base}','header']
    tracks=['SUMMARY\t8\t8\t1','CONFIG\tsynthetic',
            f'TRACK\t0\tsegment\ttrack\t0\t1\tlower\t11200000000\t{base-1000}\t{base+4_200_000_000+1000}\t{base}\t500\t10000\t0\t0\t8\t8']
    for i,(cid,sid) in enumerate(zip(ids,sources)):
        t=base+i*600_000_000;cfo=10000+300*i
        observations.append(f'{cid}\t{sid}\t0\t1\tlower\t11200000000\t{t-1000}\t{t}\t{t+1000}\t{cfo}\t1\t0.2\t0.8')
        graph.append(f'{cid}\t{t-1000}\t{t}\t{t+1000}\t1.0\t0.0\t1e-5\t0.0')
        tracks.append(f'POINT\t0\t{cid}\t{sid}\t0\t{cfo}\t{cfo}')
    paths=[]
    for name,rows in [('obs',observations),('graph',graph),('tracks',tracks)]:
        path=tmp_path/name;path.write_text('\n'.join(rows)+'\n');paths.append(str(path))
    result=subprocess.run([str(binary),*paths],capture_output=True,text=True,timeout=5,check=True)
    points=[line.split('\t') for line in result.stdout.splitlines() if line.startswith('POINT\t')]
    # Location identities bind candidate + track + alias; they are not raw
    # candidate IDs. Numeric samples and ordering must remain unchanged.
    assert len(points)==8 and len({p[1] for p in points})==8
    assert all(p[1].startswith('sha256:') and len(p[1])==71 for p in points)
    assert [float(p[2]) for p in points]==pytest.approx([.6*i for i in range(8)])
    assert [float(p[3]) for p in points]==[10000+300*i for i in range(8)]
    stages=[json.loads(line) for line in result.stderr.splitlines()]
    assert [s['stage'] for s in stages]==['read_observations','read_support','read_tracks','select','location_tracks']
    assert all(s['wall_s']>=0 and s['cpu_s']>=0 for s in stages)
