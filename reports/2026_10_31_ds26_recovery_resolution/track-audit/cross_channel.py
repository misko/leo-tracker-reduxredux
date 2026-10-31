"""Other-family fractional-epoch transfer, fixed scalar model and group splits."""
import json
import time
from pathlib import Path
import numpy as np
from audit import OUT,OLD,read,encode


def fit_scalar(witnesses):
    """A shared centered fractional-delay feature; per-track nuisance constants."""
    groups=np.repeat(np.arange(len(witnesses)),[len(w['epoch']) for w in witnesses])
    epoch=np.concatenate([w['epoch']-np.mean(w['epoch']) for w in witnesses])
    scale=max(float(epoch.std()),1e-12)
    h=np.column_stack((epoch/scale*150,np.eye(len(witnesses))[groups]*300))/150
    y=np.concatenate([w['residual_hz'] for w in witnesses])/150
    coef=np.linalg.solve(np.eye(h.shape[1])+h.T@h,h.T@y)
    return float(coef[0]*150/scale)


def rms(residual,epoch,coefficient):
    y=np.asarray(residual);pred=coefficient*(np.asarray(epoch)-np.mean(epoch))
    return dict(before=float(np.sqrt(np.mean(y*y))),after=float(np.sqrt(np.mean((y-pred)**2))),correction_rms=float(np.sqrt(np.mean(pred*pred))))


def run():
    began=time.monotonic();a=read(OUT/'audit.json');results=[]
    for case in a['cases']:
        d=read(next(OLD.glob('*'+case['case']+'/result.json')));row=d['row'];tracks={t['key']:t for t in read(row['tracks_path'])}
        obs={o['observation_id']:o for o in read(row['observations_path'])};tracking=read(row['tracking_path']);lookup={}
        for p in tracking['source']['probes']:
            if p['receiver_id']!=0:continue
            for c in p['candidates']:
                key=(p['channel'],round(c['fractional_tracking_cfo_hz'],6),round(c['fractional_margin'],10))
                lookup.setdefault(key,[]).append(c)
        def metadata(component,times):
            t=tracks[component];bytime={round(tt,8):oid for tt,oid in zip(t['times'],t['observation_ids'],strict=True)}
            result=[]
            for tt in times:
                o=obs[bytime[round(float(tt),8)]];key=(o['channel'],round(o['measured_cfo_hz'],6),round(o['fractional_margin'],10))
                result.append(min(lookup[key],key=lambda q:q['candidate_rank'])['fractional_epoch_offset_samples'])
            return np.array(result)
        families=sorted({w['norad'] for w in case['arms']['c0']['matches'] if w['receiver']==1 and not w['same_family']})
        for seed in (20261029,94721,4081):
            held=set(np.random.default_rng(seed).permutation(families)[:max(1,len(families)//3)].tolist())
            for arm,r in case['arms'].items():
                ws=[dict(w,epoch=metadata(w['component'],w['times_s'])) for w in r['matches'] if w['receiver']==1 and not w['same_family']]
                train=[w for w in ws if w['norad'] not in held];test=[w for w in ws if w['norad'] in held]
                coefficient=fit_scalar(train);target_epoch=np.array([m['fractional_epoch_offset_samples'] for m in case['metadata']])
                target=rms(r['residual_hz'],target_epoch,coefficient)
                test_metrics=[dict(component=w['component'],norad=w['norad'],points=len(w['epoch']),**rms(w['residual_hz'],w['epoch'],coefficient)) for w in test]
                poolbefore=float(np.sqrt(sum(w['points']*w['before']**2 for w in test_metrics)/sum(w['points'] for w in test_metrics)))
                poolafter=float(np.sqrt(sum(w['points']*w['after']**2 for w in test_metrics)/sum(w['points'] for w in test_metrics)))
                results.append(dict(case=case['case'],seed=seed,arm=arm,held_families=sorted(held),training_families=sorted(set(families)-held),
                    training_components=[w['component'] for w in train],coefficient_hz_per_sample=coefficient,target=target,
                    held_witnesses=test_metrics,pooled_held_before=poolbefore,pooled_held_after=poolafter))
    result=dict(protocol='Fixed one fractional-epoch coefficient,150Hz noise/feature prior,300Hz per-track nuisance. Fit only other satellite families on target receiver; whole-family randomized witness holdouts; target never fits coefficient. Residual geometry/receiver calibration inherited, so transfer is conditional.',
        GPS_used=False,RF_reads=False,rows=results,seconds=time.monotonic()-began)
    (OUT/'cross-channel.json').write_text(json.dumps(result,default=encode,indent=2)+'\n')
    for r in results:print(r['case'],r['seed'],r['arm'],'coef',round(r['coefficient_hz_per_sample'],2),'target',r['target'],'held',r['pooled_held_before'],r['pooled_held_after'])


if __name__=='__main__':run()
