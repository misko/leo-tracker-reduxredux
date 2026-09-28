"""Historical fit and untouched satellite-group validation; no DS5 RF input."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.stats import t
from empirical_prior import fit_prior,logpdf,cdf,quantile

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_26_reno_track_audit/probabilistic_history.json'


def main():
    h=json.loads(SOURCE.read_text());train=[r for r in h['pairs'] if not r['validation_group']];test=[r for r in h['pairs'] if r['validation_group']]
    assert not {r['satellite_id'] for r in train}&{r['satellite_id'] for r in test}
    model=fit_prior(train);receipts=[];scores={'old':[],'empirical':[]};coverage={k:{c:[] for c in (.9,.95,.99)} for k in scores}
    for old,b in zip(h['bins'],model['bins']):
        lo=b['lower_h'];hi=b['upper_h'];age=lo+1
        rr=[r for r in test if lo<=r['age_hours'] and (hi is None or r['age_hours']<hi)]
        x=np.array([r['equivalent_tau_s'] for r in rr]);record={'lower_h':lo,'upper_h':hi,'training_pairs':b['pairs'],'validation_pairs':len(rr),'local_weight':b['local_weight'],'supported':b['supported']}
        for name in scores:
            intervals={}
            for conf in (.9,.95,.99):
                a=(1-conf)/2
                bounds=[float(t.ppf(a,4)*old['scale_s']),float(t.ppf(1-a,4)*old['scale_s'])] if name=='old' else [quantile(model,age,a),quantile(model,age,1-a)]
                hits=((x>=bounds[0])&(x<=bounds[1])).tolist()
                coverage[name][conf].extend(hits)
                intervals[str(conf)]={'bounds_s':bounds,'coverage':float(np.mean(hits)) if hits else None}
            ll=t.logpdf(x,4,scale=old['scale_s']) if name=='old' else logpdf(model,age,x)
            scores[name].extend((-ll).tolist())
            record[name]={'intervals':intervals,'validation_mean_nll':float(np.mean(-ll)) if len(x) else None}
        record['tail_at_abs_41_9s']={'old':float(2*t.sf(41.9/old['scale_s'],4)),
            'empirical':float(cdf(model,age,[-41.9])[0]+1-cdf(model,age,[41.9])[0])}
        receipts.append(record)
    out={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'prior_source_sha256':hashlib.sha256((HERE/'empirical_prior.py').read_bytes()).hexdigest(),
         'training_pairs':len(train),'validation_pairs':len(test),'training_satellites':len({r['satellite_id'] for r in train}),
         'validation_satellites':len({r['satellite_id'] for r in test}),
         'latest_history_snapshot_ns':max(r['collected_utc_ns'] for r in h['snapshots']),
         'model':model,'bins':receipts,'validation_summary':{k:{'mean_nll':float(np.mean(scores[k])),
            'coverage':{str(c):float(np.mean(v)) for c,v in coverage[k].items()}} for k in scores}}
    (HERE/'calibration.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out['validation_summary'],indent=2))
    print('12-24h',json.dumps(receipts[2],indent=2))


if __name__=='__main__':main()
