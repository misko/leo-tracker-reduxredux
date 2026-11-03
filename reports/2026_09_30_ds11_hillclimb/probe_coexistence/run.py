"""Fixed-metadata, common-IQ-sample comparison of two pilot contributions."""
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import model

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
ROOT=HERE.parents[2]
BULK=Path('/srv/bulk/leo')
sys.path.insert(0,str(ROOT/'reports/2026_09_27_ds7_header'))
from recover import geometry,references


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)


def matrices(row):
    epochs=[c['integer_epoch_sample']+c['fractional_epoch_offset_samples'] for c in row['candidates']]
    count=int(np.ceil(max(epochs)+302*4.4e-6*model.FS))+1
    assert count<=100000
    times=np.arange(count)/model.FS
    _,bins,center=geometry(row['edge']);_,_,pilots=references(row['edge'])
    frequency=np.fft.fftfreq(1024,1/240e6)[bins]-center
    designs=[];controls=[];training=np.ones(count,bool);held=np.ones(count,bool)
    for epoch,candidate in zip(epochs,row['candidates'],strict=True):
        cfo=candidate['fractional_tracking_cfo_hz']
        keep=abs(frequency+cfo)<=.45*model.FS
        assert sum(keep)>=2
        a,t,h=model.design(times,epoch,cfo,frequency[keep],pilots[:,keep])
        c,_,_=model.design(times,epoch,cfo,frequency[keep],pilots[:,keep],roll=11)
        designs.append(a);controls.append(c);training&=t;held&=h
    if len(designs)==1:
        families=dict(single=designs[0],rolled=controls[0])
    else:
        families=dict(a=designs[0],b=designs[1],joint=np.column_stack(designs),
                      a_rolled_b=np.column_stack((designs[0],controls[1])),
                      b_rolled_a=np.column_stack((designs[1],controls[0])))
    return families,training,held


def prepare():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    side_path=HILL/'source_consistency/source_groups.json';side=read(side_path)['scans']['0']
    wave=HILL/'norad65512_waveform';old=read(wave/'manifest.json');saved=read(wave/'local/extraction.json')
    for path,h in old['sources'].items():assert digest(path)==h,path
    assert saved['plan_sha256']==digest(wave/'manifest.json')
    store=ScannerTrackingInputStore(BULK)
    try: raw=store.load(side['session_id'])
    finally: store.close()
    assert raw.input_manifest_sha256==old['capture']['manifest_sha256'] and raw.sample_rate_hz==model.FS
    assert raw.analysis_manifest_sha256==old['analysis_manifest_sha256']
    points={p.candidate_id:p for p in project_scanner_candidates(raw)}
    probes={(p.receiver_id,p.visit_index,p.probe_index):p for p in raw.probes}
    groups={}
    for rows in side['tracks'].values():
        for p in rows:
            if p['training']:groups.setdefault(p['source_group_id'],set()).add(p['candidate_id'])
    selected=[];considered=[]
    for group,ids in sorted(groups.items()):
        if len(ids)<2:continue
        ids=sorted(ids)[:2];a,b=[points[k] for k in ids]
        assert a.source_group_id==b.source_group_id==group
        assert (a.receiver_id,a.visit_index,a.probe_index)==(b.receiver_id,b.visit_index,b.probe_index)
        probe=probes[a.receiver_id,a.visit_index,a.probe_index]
        candidates=[next(c for c in probe.candidates if c.candidate_rank==p.candidate_rank) for p in (a,b)]
        row=dict(source_group_id=group,candidate_ids=ids,visit=a.visit_index,receiver_id=a.receiver_id,
                 probe_index=a.probe_index,probe_start_ms=probe.probe_start_ms,edge=probe.edge,
                 actual_rf_hz=probe.actual_rf_hz,candidates=[dataclasses.asdict(c) for c in candidates])
        _,training,held=matrices(row)
        eligible=int(sum(training))>=512 and int(sum(held))>=256
        considered.append(dict(source_group_id=group,training_samples=int(sum(training)),held_samples=int(sum(held)),eligible=eligible))
        if eligible:selected.append(dict(row,ordinal=len(selected)))
        if len(selected)==6:break
    assert len(selected)==6
    controls=[]
    for ordinal in (0,55,110):
        r=old['rows'][ordinal];e=saved['rows'][ordinal]
        assert e['status']=='ok' and digest(e['path'])==e['sha256']
        controls.append(dict(ordinal=ordinal,candidates=[r['candidate']],edge=r['edge'],path=e['path'],sha256=e['sha256']))
    paths=[Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md',side_path,
           wave/'manifest.json',wave/'local/extraction.json']
    paths += [Path(inspect.getfile(obj)) for obj in (ScannerTrackingInputStore,AdaptiveHopIqStore,project_scanner_candidates)]
    sources=dict(old['sources']);sources.update({str(p):digest(p) for p in paths})
    plan=dict(schema='ds11-common-probe-pilot-comparison/v1',session_id=side['session_id'],
              manifest_sha256=raw.input_manifest_sha256,analysis_manifest_sha256=raw.analysis_manifest_sha256,
              rows=selected,considered=considered,controls=controls,sources=sources,reference_used=False)
    write(HERE/'plan.json',plan)
    print(json.dumps(dict(selected=len(selected),considered=len(considered),counts=considered)))


def worker():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    plan=read(HERE/'plan.json')
    for path,h in plan['sources'].items():assert digest(path)==h,path
    store=AdaptiveHopIqStore(BULK,read_only=True)
    try:
        published=store.inspect(plan['session_id'])
        assert published.manifest_sha256==plan['manifest_sha256']
        with store.reader(plan['session_id'],expected=published) as reader:
            for row in plan['rows']:
                stem=f"pair-{row['ordinal']:02d}"
                write(HERE/'local'/f'{stem}.active.json',dict(status='active'))
                try:
                    _,samples=reader.read_visit_ci16(row['visit'])
                    start=row['probe_start_ms']*model.FS//1000
                    iq=samples[start:start+100000,row['receiver_id'],:].copy()
                    assert iq.shape==(100000,2) and iq.dtype==np.dtype('<i2')
                    path=HERE/'local'/f'{stem}.npy';np.save(path,iq,allow_pickle=False)
                    families,train,held=matrices(row);n=len(train)
                    y=iq[:n,0].astype(float)+1j*iq[:n,1]
                    result=dict(status='ok',scores=model.compare(y,families,train,held),
                                training_samples=int(sum(train)),held_samples=int(sum(held)),
                                excerpt_path=str(path),excerpt_sha256=digest(path))
                except Exception as error:result=dict(status='failed',reason=f'{type(error).__name__}: {error}')
                write(HERE/'local'/f'{stem}.json',result)
    finally:store.close()
    for row in plan['controls']:
        stem=f"control-{row['ordinal']:03d}"
        write(HERE/'local'/f'{stem}.active.json',dict(status='active'))
        try:
            assert digest(row['path'])==row['sha256']
            iq=np.load(row['path'],allow_pickle=False);families,train,held=matrices(row);n=len(train)
            result=dict(status='ok',scores=model.compare(iq[:n,0].astype(float)+1j*iq[:n,1],families,train,held),
                        training_samples=int(sum(train)),held_samples=int(sum(held)))
        except Exception as error:result=dict(status='failed',reason=f'{type(error).__name__}: {error}')
        write(HERE/'local'/f'{stem}.json',result)


def batch():
    (HERE/'local').mkdir()
    command=['timeout','--kill-after=5s','120s','nice','-n','19',sys.executable,str(Path(__file__)),'worker']
    started=time.monotonic()
    with (HERE/'worker.log').open('x') as log:done=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    write(HERE/'receipt.json',dict(exit_code=done.returncode,elapsed_s=time.monotonic()-started,
                                 command=command,plan_sha256=digest(HERE/'plan.json')))
    rows={}
    for stem in [f'pair-{i:02d}' for i in range(6)]+[f'control-{i:03d}' for i in (0,55,110)]:
        path=HERE/'local'/f'{stem}.json'
        rows[stem]=read(path) if path.exists() else dict(status='failed' if (HERE/'local'/f'{stem}.active.json').exists() else 'not_attempted')
    paths=[HERE/'plan.json',HERE/'receipt.json']+sorted((HERE/'local').glob('*.json'))
    write(HERE/'outcome.json',dict(rows=rows,sources={str(p):digest(p) for p in paths},position_fits=0))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    {'prepare':prepare,'worker':worker,'batch':batch}[sys.argv[1]]()
