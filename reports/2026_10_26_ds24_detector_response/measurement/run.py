"""Exact-scope64 response control in the immutable deployed interpreter."""
import time
STARTED=time.monotonic()
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import unittest
import numpy as np
import refiner

HERE=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/ds24-candidate-continuity-r01/single_source')
DEPLOYED=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src/leo')
spec=importlib.util.spec_from_file_location('response_old_single',OLD/'run.py')
single=importlib.util.module_from_spec(spec);spec.loader.exec_module(single)
fixture=single.fixture
FRESH_SEED=2026102802
PRIOR_PREPARATION_SECONDS=1.0  # Preserved import-only missing-SciPy attempt; no detector/scoring calls.
FRESH=[dict(index=i,base_cfo_hz=f,rate_hz_s=r,time_s=float(t))
       for i,(f,r,t) in enumerate((f,r,t) for f in (100037.,-100113.) for r in (200.,-200.) for t in (0,7))]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):fixture.write(p,v)


def choose(rows):
    candidates=[c for c in rows if c['fractional_epoch_status']=='complete' and all(c[k] is not None for k in
        ('fractional_epoch_offset_samples','fractional_tracking_cfo_hz','fractional_exact_score','fractional_control_score','fractional_margin'))
        and c['fractional_margin']>=.025]
    return max(candidates,key=lambda c:(c['fractional_margin'],-c['candidate_rank'])) if candidates else None


def alarm(seconds):
    if seconds<=0:raise TimeoutError('original300-second numerical cap exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('frozen response deadline')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def synthesize_fresh(definition):
    d=definition;source=dict(name='A',cfo0=d['base_cfo_hz'],rate=d['rate_hz_s'],
        amplitude=1000.,phase=.3,epoch=127)
    local=np.arange(fixture.COUNT)/fixture.RATE
    clean=source['amplitude']*fixture.waveform('sampled_deployed',127)*fixture.carrier(source,d['time_s']+local)
    rng=np.random.default_rng(np.random.SeedSequence([FRESH_SEED,d['index']]))
    noise=300/np.sqrt(2)*(rng.normal(size=(fixture.COUNT,2))+1j*rng.normal(size=(fixture.COUNT,2)))
    values=clean[:,None]+noise;iq=np.stack((values.real,values.imag),axis=-1)
    clipped=int(np.count_nonzero((iq < -32768)|(iq > 32767)))
    if clipped:raise ValueError('ADC clipping')
    iq=np.rint(iq).astype('<i2')
    return iq,dict(iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),
        noise_sha256=hashlib.sha256(noise.tobytes()).hexdigest(),clipping_samples=clipped,
        source=source,definition=d,seed=[FRESH_SEED,d['index']],waveform_law='sampled_deployed')


def attribution():
    rows=[]
    for visit in range(24):
        slot=json.loads((OLD/'slots'/f'single_source_{visit:02}.json').read_text())
        for rx in slot['receivers']:
            p=choose(rx['candidates'])
            if p is None:
                rows.append(dict(visit=visit,receiver=rx['receiver_id'],status='no_original_candidate'));continue
            truth=100000.+200.*(visit+.01)
            rows.append(dict(visit=visit,receiver=rx['receiver_id'],status='complete',candidate_rank=p['candidate_rank'],
                acquired_cfo_hz=p['acquired_cfo_hz'],integer_residual_cfo_hz=p['residual_cfo_hz'],
                fractional_residual_cfo_hz=p['fractional_residual_cfo_hz'],final_cfo_hz=p['fractional_tracking_cfo_hz'],
                generated_midpoint_cfo_hz=truth,acquired_error_hz=p['acquired_cfo_hz']-truth,
                final_error_hz=p['fractional_tracking_cfo_hz']-truth,
                integer_epoch_sample=p['epoch_sample'],fractional_epoch_offset_samples=p['fractional_epoch_offset_samples']))
    complete=[r for r in rows if r['status']=='complete']
    proceed=len(complete)==48 and all(r['fractional_residual_cfo_hz']==0 for r in complete) and max(abs(r['acquired_error_hz']) for r in complete)>4
    write(HERE/'attribution.json',dict(rows=rows,all48_final_errors_inherited_from_acquisition=proceed,
        within_window_total_chirp_hz=4.,new_detector_calls=0))
    return proceed


def prepare():
    identity=fixture.detector_identity()
    seal=json.loads((OLD/'RF_seal.json').read_text())
    for p,digest in seal['files'].items():
        if sha(p)!=digest:raise ValueError('old fixture changed: '+p)
    iq,meta=single.synthesize(0)
    stored=json.loads((OLD/'slots/single_source_00.json').read_text())['input']
    if meta['iq_sha256']!=stored['iq_sha256']:raise ValueError('old IQ generator port does not replay')
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_refiner.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise RuntimeError('owned tests failed')
    write(HERE/'preparation.json',dict(all_passed=True,seconds=time.monotonic()-STARTED+PRIOR_PREPARATION_SECONDS,tests=result.testsRun,
        prior_import_failure_seconds_charged=PRIOR_PREPARATION_SECONDS,
        identity=identity,solver_dependency='numpy_only',old_IQ_hash_smoke=True,new_detector_calls=0,
        actual_control_refinement_evaluations=0))


def freeze():
    if (HERE/'protocol.json').exists():raise FileExistsError('protocol already frozen')
    paths=[HERE/'refiner.py',HERE/'run.py',HERE/'test_refiner.py',HERE/'PROTOCOL.md',HERE/'preparation.json',
        HERE.parent/'COORDINATOR_PLAN.md',HERE.parent/'SOURCE_REVIEW.md',OLD/'run.py',OLD/'protocol.json',OLD/'RF_seal.json',
        fixture.HERE/'experiment.py',fixture.OLD/'control.py',fixture.AUTH/'replay_metadata.json']
    paths += [HERE.parent/'measurement_preparation.log',HERE.parent/'measurement_preparation02.log']
    paths+=sorted((OLD/'slots').glob('single_source_*.json'))
    paths+=[DEPLOYED/p for p in ('analysis/starlink/acquisition.py','analysis/starlink/fast_scan_scores.py',
        'analysis/starlink/fast_scan_fractional.py','analysis/starlink/templates.py','scanner/fast_scan_detector.py',
        'scanner/fast_scan_analysis.py')]
    write(HERE/'protocol.json',dict(files={str(p):sha(p) for p in paths},old_visits=list(range(24)),fresh=FRESH,
        fresh_seed=FRESH_SEED,maximum_new_paired_detector_calls=8,original_replayed_detector_calls=0,
        old_receiver_slots=48,fresh_receiver_slots=16,total_receiver_slots=64,
        numerical_cap_seconds=300.,preparation_seconds=json.loads((HERE/'preparation.json').read_text())['seconds'],
        worker_count=1,blas_threads=1,score_symbols=list(range(2,66)),original_DFT_size=512,
        original_bin_half_cell=True,independent_frequency_tolerance_hz=.01,score_tolerance=1e-10,
        boundary_distance_hz=.05,old_candidate_epoch_window_gate_preserved=True,
        optimize_exact_and_control_symmetrically=True,within_symbol_redemodulation_changed=False))


def run():
    from leo.scanner.fast_scan_analysis import production_glrt
    if (HERE/'execution.json').exists() or (HERE/'results').exists():raise FileExistsError('no retries')
    p=json.loads((HERE/'protocol.json').read_text())
    for path,digest in p['files'].items():
        if sha(path)!=digest:raise ValueError('frozen source/input changed: '+path)
    receipt=json.loads((HERE.parent/'audit/measurement_preflight.json').read_text())
    if not receipt['all_passed'] or receipt['protocol_sha256']!=sha(HERE/'protocol.json'):
        raise ValueError('exact B preflight required')
    before=fixture.detector_identity();deadline=STARTED+300.-p['preparation_seconds'];records=[];calls=0
    def failed_pair(name,status,error):
        for rx in (0,1):
            file=HERE/'results'/f'{name}_RX{rx}.json'
            write(file,dict(name=name,receiver=rx,status=status,error=error))
            records.append(dict(name=name,receiver=rx,status=status,error=error,file=str(file),sha256=sha(file)))
    def finish(status='terminal'):
        present={(r['name'],r['receiver']) for r in records}
        for name in [f'old24_{i:02}' for i in range(24)]+[f'fresh_{i:02}' for i in range(8)]:
            for rx in (0,1):
                if (name,rx) not in present:
                    file=HERE/'results'/f'{name}_RX{rx}.json'
                    write(file,dict(name=name,receiver=rx,status='not_attempted',error=status))
                    records.append(dict(name=name,receiver=rx,status='not_attempted',file=str(file),sha256=sha(file)))
        after=fixture.detector_identity()
        write(HERE/'execution.json',dict(status=status,records=records,total_receiver_slots=64,
            completed=sum(r['status']=='complete' for r in records),new_paired_detector_calls=calls,
            old_detector_replays=0,identity_before=before,identity_after=after,identity_unchanged=before==after,
            cumulative_worker_seconds=time.monotonic()-STARTED+p['preparation_seconds'],
            no_candidate_epoch_or_gate_reselection=True,graph_fits=0,position_fits=0,original_IQ_read=False))
        files=[q for q in HERE.rglob('*') if q.is_file() and q.name!='RF_seal.json'
               and '__pycache__' not in q.parts and '.pytest_cache' not in q.parts]
        write(HERE/'RF_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),all_selected_terminal=True,
            files={str(q):sha(q) for q in files}))
        print('TERMINAL '+json.dumps(dict(status=status,completed=sum(r['status']=='complete' for r in records),
            slots=64,new_detector_calls=calls,cumulative_seconds=time.monotonic()-STARTED+p['preparation_seconds'])),flush=True)
    try:proceed=attribution()
    except Exception as exc:
        finish('attribution_failed: '+repr(exc));return
    if not proceed:
        finish('stopped_attribution_not_confirmed');return
    def correct(name,iq,receivers,metadata,truth):
        for rx in receivers:
            row=dict(name=name,receiver=rx['receiver_id'],input=metadata,generated_truth=truth)
            began=time.monotonic();peak=choose(rx['candidates']);row['original_selected_candidate']=peak
            try:
                alarm(deadline-time.monotonic())
                if peak is None:raise ValueError('no_original_gate_passing_candidate; no replacement')
                values=iq[:,int(rx['receiver_id']),0].astype(float)+1j*iq[:,int(rx['receiver_id']),1].astype(float)
                result,workspace=refiner.refine(values,fixture.RATE,'upper',peak['acquired_cfo_hz'],peak['epoch_sample'],
                    peak['fractional_epoch_offset_samples'],peak['fractional_residual_cfo_hz'],
                    peak['fractional_exact_score'],peak['fractional_control_score'])
                row.update(status='complete',result=result)
                path=HERE/'correlations'/f"{name}_RX{rx['receiver_id']}.npz";path.parent.mkdir(exist_ok=True)
                np.savez(path,**workspace);row['correlations_file']=str(path);row['correlations_sha256']=sha(path)
            except Exception as exc:row.update(status='failed',error=repr(exc))
            finally:signal.setitimer(signal.ITIMER_REAL,0)
            row['seconds']=time.monotonic()-began
            file=HERE/'results'/f"{name}_RX{rx['receiver_id']}.json";write(file,row)
            records.append(dict(name=name,receiver=rx['receiver_id'],status=row['status'],file=str(file),sha256=sha(file)))
    for visit in range(24):
        try:
            alarm(deadline-time.monotonic());iq,meta=single.synthesize(visit)
            old=json.loads((OLD/'slots'/f'single_source_{visit:02}.json').read_text())
            if meta['iq_sha256']!=old['input']['iq_sha256']:raise ValueError('old IQ hash mismatch')
        except Exception as exc:
            failed_pair(f'old24_{visit:02}','input_failed',repr(exc));continue
        finally:signal.setitimer(signal.ITIMER_REAL,0)
        correct(f'old24_{visit:02}',iq,old['receivers'],meta,dict(midpoint_cfo_hz=100000.+200*(visit+.01),time_s=float(visit),rate_hz_s=200.))
    print('OLD24_COMPLETE '+json.dumps(dict(receiver_slots=48,seconds=time.monotonic()-STARTED)),flush=True)
    for d in FRESH:
        name=f"fresh_{d['index']:02}";slot=dict(name=name,definition=d);began=time.monotonic()
        try:
            alarm(min(20.,deadline-time.monotonic()));iq,meta=synthesize_fresh(d);calls+=1
            receivers=[x.model_dump(mode='json') for x in production_glrt(fixture.window(iq),(0,1))]
            slot.update(status='complete',input=meta,receivers=receivers)
        except Exception as exc:slot.update(status='failed',error=repr(exc))
        finally:signal.setitimer(signal.ITIMER_REAL,0)
        slot['seconds']=time.monotonic()-began;write(HERE/'fresh_slots'/f'{name}.json',slot)
        if slot['status']=='complete':
            correct(name,iq,receivers,meta,dict(midpoint_cfo_hz=d['base_cfo_hz']+d['rate_hz_s']*(d['time_s']+.01),
                time_s=d['time_s'],rate_hz_s=d['rate_hz_s'],base_cfo_hz=d['base_cfo_hz']))
        else:
            failed_pair(name,'detector_failed',slot['error'])
    finish()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','freeze','run'))
    args=parser.parse_args();{'prepare':prepare,'freeze':freeze,'run':run}[args.command]()
