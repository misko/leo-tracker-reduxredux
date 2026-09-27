"""Receiver/channel sensitivity audit; positions selected without roof truth."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_track_scale'))
from run_scale import (ScaledObjective, TleArchiveReader, exclude_labelled_starlink_debris,
                       parse_element_sets, propagate_candidate_states)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    parent=REPORTS/'2026_09_27_ds6_track_scale'
    old=json.loads((parent/'protocol.json').read_text())
    dependencies={**old['dependencies'],'2026_09_27_ds6_track_scale/run_scale.py':digest(parent/'run_scale.py')}
    inputs={}
    for name in old['inputs']:
        for directory,filename in [('2026_09_27_ds6_common_rate_validation',name),
            ('2026_09_27_ds6_track_scale',name.replace('-plan','')),
            ('2026_09_27_ds6_cfo_transfer',name.replace('-plan',''))]:
            path=REPORTS/directory/filename;inputs[str(path.relative_to(REPORTS))]=digest(path)
    protocol=dict(source_sha256=digest(Path(__file__)),dependencies=dependencies,inputs=inputs,
        sessions=[name.removesuffix('-plan.json') for name in old['inputs']],center=old['center'],
        groups='all, each available receiver alone, leave each available channel out; no reference-based selection',
        calibration='Reuse frozen training-only scales; catalogue shortlist and visit masks unchanged',
        optimization='Three starts at calibrated winner position, tau=previous,-2,+2; local +/-12 km and +/-5 s',
        selection='Maximize training likelihood per group; held never ranks points',
        evaluation='Report held prediction on included and omitted groups at group fit vs original all-track fit',
        limitation='Diagnostic group fits retain all-track training calibration and initialization; not independent validation')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def load(session):
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in {**protocol['dependencies'],**protocol['inputs']}.items():assert digest(REPORTS/name)==value
    data=json.loads((REPORTS/'2026_09_27_ds6_common_rate_validation'/f'{session}-plan.json').read_text())
    previous=json.loads((REPORTS/'2026_09_27_ds6_track_scale'/f'{session}.json').read_text())
    transfer=json.loads((REPORTS/'2026_09_27_ds6_cfo_transfer'/f'{session}.json').read_text())
    chosen={}
    for stage in transfer['stages']:
        for key,values in stage['shortlists'].items():chosen.setdefault(key,set()).update(values)
    scales={r['track_id']:r['sigma'] for r in previous['calibration']}
    tracks=[]
    for t in data['tracks']:
        if t['track_id'] not in chosen:continue
        t=dict(t,t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=np.array(t['training_mask'],dtype=bool),sigma=scales[t['track_id']])
        t['centered_t']=t['t']-t['t'][t['mask']].mean();tracks.append(t)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000)
    assert snap.digest==data['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    def banks(taus):
        return {t['track_id']:propagate_candidate_states(cat,np.array(sorted(chosen[t['track_id']])),data['start_utc_ns'],t['t'],taus) for t in tracks}
    bank=banks(np.arange(-5.,5.001,.25))
    return protocol,tracks,bank,banks,len(cat.satellite_numbers),np.array(previous['arms']['training_scale']['best']['x'])


def groups(tracks):
    selections={'all':tracks}
    for rx in sorted({t['receiver_id'] for t in tracks}):
        selections[f'only_rx{rx}']=[t for t in tracks if t['receiver_id']==rx]
    for ch in sorted({t['channel'] for t in tracks}):
        subset=[t for t in tracks if t['channel']!=ch]
        if subset:selections[f'without_ch{ch}']=subset
    return selections


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    protocol,tracks,bank,banks,size,x0=load(session)
    center=protocol['center'];selections=groups(tracks);results={}
    all_model=ScaledObjective(tracks,bank,center,size,[])
    baseline_exact=banks(np.array([x0[2]]))
    for name,subset in selections.items():
        model=ScaledObjective(subset,bank,center,size,[])
        ids={t['track_id'] for t in subset}
        omitted=[t for t in tracks if t['track_id'] not in ids]
        other=ScaledObjective(omitted,bank,center,size,[]) if omitted else None
        runs=[]
        for tau in [x0[2],-2.,2.]:
            initial=x0.copy();initial[2]=tau
            fit=minimize(lambda x:-model.evaluate(x)['train'],initial,method='L-BFGS-B',
                bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],
                options=dict(maxiter=70,maxfun=650,ftol=1e-10,gtol=1e-5,eps=1e-4))
            score=model.evaluate(fit.x);lat,lon=model.coordinates(fit.x)
            runs.append(dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=score['train'],held=score['held'],
                success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),
                bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.,5.])))))
        best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);exact=banks(np.array([x[2]]))
        before=model.evaluate(x0,exact_banks=baseline_exact);after=model.evaluate(x,exact_banks=exact)
        held_other_before=other.evaluate(x0,exact_banks=baseline_exact)['held'] if other else None
        held_other_after=other.evaluate(x,exact_banks=exact)['held'] if other else None
        approx=all_model.evaluate(x)['predictions'];verified=all_model.evaluate(x,exact_banks=exact)['predictions']
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(approx,verified,strict=True))
        results[name]=dict(best=best,runs=runs,track_ids=sorted(ids),tracks=len(subset),
            shift_from_all_km=float(np.linalg.norm(x[:2]-x0[:2])),
            included_held_gain=after['held']-before['held'],
            omitted_held_gain=held_other_after-held_other_before if other else None,
            maximum_interpolation_error_hz=deviation)
        output.write_text(json.dumps(dict(session_id=session,complete=len(results)==len(selections),
            protocol_sha256=digest(HERE/'protocol.json'),baseline_x=x0.tolist(),groups=results),indent=2)+'\n')
        print(json.dumps(dict(session=session,group=name,**{k:v for k,v in results[name].items() if k not in ['runs','track_ids'] })),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session')
    args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
