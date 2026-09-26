"""Freeze cross-scan support calibration, then compare held-pilot pair scores."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from support_calibration import fit,predict,log_score
from timing_trial import options,evaluate

HERE=Path(__file__).resolve().parent
OUT=HERE/'support-trial'

def observations():
    result={}
    # Prefer longer-overlap extraction if a visit was sampled by both plans.
    for root in [HERE,HERE/'long-overlap']:
        for path in sorted(root.glob('scan-fw-*.json')):
            data=json.loads(path.read_text());rows=data['rows']
            for visit in sorted({r['visit'] for r in rows}):
                modes=[sorted([r for r in rows if r['visit']==visit and r['mode']==m],key=lambda r:r['start_ms']) for m in (0,1)]
                if not modes[1]:continue
                assert len(modes[0])==len(modes[1])==6
                means={};train_R=[]
                for subset in ('train','held'):
                    angles=np.array([r['coefficients'][subset]['phase_rad'] for r in modes[1]])-np.array([r['coefficients'][subset]['phase_rad'] for r in modes[0]])
                    means[subset]=np.mean(np.exp(1j*angles))
                train_R=np.minimum(*[np.array([r['coefficients']['train']['R'] for r in mode]) for mode in modes])
                sid=data['session_id'] if 'session_id' in data else rows[0]['session_id']
                result[sid,visit]=dict(session_id=sid,visit=visit,feature=float(np.mean(train_R)*abs(means['train'])),train_phase=float(np.angle(means['train'])),held_phase=float(np.angle(means['held'])),error_rad=float(np.angle(means['held']*means['train'].conjugate())),source=str(path.relative_to(HERE)),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return list(result.values())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);args=parser.parse_args()
    OUT.mkdir(exist_ok=True);rows=observations();sid=['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3'][args.scan]
    calibration=fit(rows,sid)
    target=[r for r in rows if r['session_id']==sid];k=predict(calibration['parameters'],[r['feature'] for r in target]);err=np.array([r['error_rad'] for r in target])
    validation=dict(dwells=len(target),mean_calibrated_score=float(np.mean(log_score(err,k))),mean_constant_score=float(np.mean(log_score(err,calibration['constant_kappa']))),mean_fixed_one_score=float(np.mean(log_score(err,1))),median_kappa=float(np.median(k)),minimum_kappa=float(min(k)),maximum_kappa=float(max(k)))
    protocol=dict(excluded_scan=sid,feature='mean of min(mode0 train R, mode1 train R) times train DD circular concentration across six windows',target='held-pilot minus training-pilot circular dwell mean; noisy internal agreement, not geometric phase error',model='kappa=8*sigmoid(a+b*x), b>=0; weak fixed ridge; equal scan weight; one dwell per sample',evaluation='all selected long-overlap dwells; held-pilot phase only; same CFO banks/folds/shortlists as timing trial',arms=['fixed_one','development_constant','support_calibrated'],calibration=calibration,validation=validation,source_rows=rows)
    (OUT/(sid+'-protocol.json')).write_text(json.dumps(protocol,indent=2)+'\n')
    output=[]
    lookup={(r['session_id'],r['visit']):r for r in rows}
    for fold in (0,1):
        previous=json.loads((HERE/'timing-trial'/f'{sid}-f{fold}-q33.json').read_text());obs=previous['observations'];train=np.array(previous['phase_training_mask'],bool)
        data=[lookup[sid,r['visit']] for r in obs];y=np.array([r['held_phase'] for r in data]);x=np.array([r['feature'] for r in data])
        banks=[dict(np.load(HERE/'timing-trial'/f'{sid}-f{fold}-{tid[7:19]}.npz')) for tid in previous['track_ids']]
        for sigma in (100,200):
            a,b=[options(bank,sigma,33) for bank in banks]
            for arm,concentration in [('fixed_one',1.),('development_constant',calibration['constant_kappa']),('support_calibrated',predict(calibration['parameters'],x))]:
                scored=evaluate(a,b,y,train,np.array([r['f0'] for r in obs]),np.array([r['f1'] for r in obs]),concentration)
                scored.update(fold=fold,sigma=sigma,arm=arm);output.append(scored)
                print(sid,fold,sigma,arm,'CFO gain',round(scored['cfo_gain'],6),'phase gain',round(scored['phase_gain_vs_constant'],6),flush=True)
        (OUT/(sid+'.json')).write_text(json.dumps(dict(protocol=protocol,experiments=output),indent=2)+'\n')
    print(sid,'calibration',json.dumps(validation),flush=True)

if __name__=='__main__':main()
