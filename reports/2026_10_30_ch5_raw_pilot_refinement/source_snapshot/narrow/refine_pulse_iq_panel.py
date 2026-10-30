"""Bounded pilot-only refinement of both complete CH5 graph fragments."""
import argparse,hashlib,time,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from debug_fast_graph_unassociated import read,write


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(args):
    d=read(args.diagnostic);m=read(args.measurements);native={r['observation_id']:r for r in m['native_measurements']}
    components={f['component'] for f in d['arms'][0]['fragments'] if f['shared_family'] or not f['calibration_points']}
    points=[]
    for o in d['observations']:
        if o['component'] not in components:continue
        n=native[o['observation_id']];c=n['candidate']
        points.append(dict(observation_id=o['observation_id'],component=o['component'],time_s=o['time_s'],
            visit_index=o['visit_index'],receiver_id=o['native_receiver_id'],sample_start=o['valid_start_counter'],
            iq_sha256=n['iq_sha256'],edge=n['edge'],candidate_rank=c['candidate_rank'],
            CFO_hz=c['fractional_tracking_cfo_hz'],epoch_sample=c['epoch_sample']+c['fractional_epoch_offset_samples']))
    if len(points)>100:raise ValueError('bounded 100-point replay budget exceeded')
    args.output.mkdir(parents=True,exist_ok=False)
    # The exported plan contains no orbit, location, pulse fit or target residual.
    write(args.output/'plan.json',dict(points=points,sample_rate_hz=d['job']['sample_rate_hz'],window_samples=200000,
        input_manifest_digest=d['job']['identities'][1],workers=4,seconds_per_worker=900,
        methods=['fixed_epoch','joint_all','joint_odd','joint_even'],joint_starts=1,joint_iterations=16,
        frequency_radius_hz=800,scout_radius_hz=600,epoch_radius_samples=.75,code_rate_radius_ppm=40,
        selection='both complete original interleaved graph fragments; no point selection by residual',
        diagnostic_sha256=sha(args.diagnostic),measurements_sha256=sha(args.measurements),
        source_sha256=sha(__file__),no_GPS_or_TLE_in_measurement_plan=True,
        odd_even_independently_fitted=True,odd_even_share_archived_full_window_nomination=True))
    print('frozen',len(points),'points',flush=True)


def worker(args):
    from fast_local_pilot_refinement import FastPilotWorkspace
    plan=read(args.output/'plan.json');panel=args.output/'panel';meta=read(panel/'manifest.json')
    if meta['plan_sha256']!=sha(args.output/'plan.json'):raise ValueError('plan changed')
    started=time.monotonic();rows=[]
    points=sorted(meta['points'],key=lambda p:p['visit_index'])
    for k,p in enumerate(points):
        if k%plan['workers']!=args.worker_id:continue
        path=panel/p['array']
        if sha(path)!=p['array_sha256']:raise ValueError('IQ export changed')
        a=np.load(path,allow_pickle=False);y=a[:,0].astype(float)+1j*a[:,1].astype(float)
        w=FastPilotWorkspace(y,meta['sample_rate_hz'],p['edge'],p['epoch_sample']);center=p['CFO_hz'];fits={}
        fits['fixed_epoch']=w.frequency_fit(center)
        for subset in ('all','odd','even'):
            fit=w.fast_joint_fit(center,subset=subset,starts=plan['joint_starts'],iterations=plan['joint_iterations'],
                radius=plan['frequency_radius_hz'],scout_radius=plan['scout_radius_hz'])
            # Evaluate a fitted subset on its complementary frames without refitting.
            if subset!='all':
                other='even' if subset=='odd' else 'odd'
                fit['complement_score']=float(w.evaluate([fit['CFO_hz']],fit['offset_samples'],fit['modulation_ppm'],subset=other)[0])
                fit['complement_score_at_original']=float(w.evaluate([center],subset=other)[0])
            fit['effective_time_from_probe_start_s']=w.effective_time(fit);fits['joint_'+subset]=fit
        row=dict(point=p,methods=fits,original_local_score=float(w.evaluate([center])[0]),
            original_local_control=float(w.evaluate([center],control=True)[0]))
        rows.append(row);write(args.output/f"worker-{args.worker_id}-point-{k:03d}.json",row)
        print('worker',args.worker_id,'point',k,'delta Hz',round(fits['joint_all']['CFO_hz']-center,2),
            'odd-even',round(fits['joint_odd']['CFO_hz']-fits['joint_even']['CFO_hz'],2),'seconds',round(time.monotonic()-started,1),flush=True)
    write(args.output/f'worker-{args.worker_id}.json',dict(rows=rows,seconds=time.monotonic()-started,
        plan_sha256=sha(args.output/'plan.json'),panel_manifest_sha256=sha(panel/'manifest.json'),
        source_hashes={str(p):sha(p) for p in [Path(__file__),Path(__file__).with_name('fast_local_pilot_refinement.py'),Path(__file__).with_name('local_pilot_refinement.py')]},
        no_GPS_TLE_or_satellite_input=True))


def run(args):
    from stress_joint_attachment import supervise
    plan=read(args.output/'plan.json');terminal=[]
    def launch(k):
        r=supervise([sys.executable,__file__,'worker','--output',str(args.output),'--worker-id',str(k)],
            args.output/f'worker-{k}.log',plan['seconds_per_worker'])
        r=dict(worker_id=k,**r);write(args.output/f'worker-{k}-terminal.json',r);return r
    with ThreadPoolExecutor(max_workers=plan['workers']) as pool:
        for f in as_completed([pool.submit(launch,k) for k in range(plan['workers'])]):terminal.append(f.result())
    write(args.output/'execution.json',terminal)
    if not all(r['status']=='complete' for r in terminal):raise ValueError('incomplete bounded replay; inspect terminal receipts')
    workers=[read(args.output/f'worker-{k}.json') for k in range(plan['workers'])];rows=[r for w in workers for r in w['rows']]
    expected={p['observation_id'] for p in plan['points']};actual=[r['point']['observation_id'] for r in rows]
    if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('incomplete or duplicate measurement result')
    write(args.output/'result.json',dict(rows=sorted(rows,key=lambda r:r['point']['time_s']),
        all_original_selected_points_present=True,plan_sha256=sha(args.output/'plan.json'),
        worker_hashes={str(args.output/f'worker-{k}.json'):sha(args.output/f'worker-{k}.json') for k in range(plan['workers'])},
        no_GPS_TLE_or_satellite_in_local_refinement=True,production_measurements_unchanged=True))
    print('all',len(rows),'measurements complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','worker','run'])
    for name in ('diagnostic','measurements','output'):p.add_argument('--'+name,type=Path,required=name=='output')
    p.add_argument('--worker-id',type=int);a=p.parse_args();globals()[a.mode](a)
