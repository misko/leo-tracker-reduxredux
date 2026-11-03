"""Compare fragment clocks on exactly matched source-clock held candidates.

Diagnostic only: same earlier source boundary, same quadratic and loss; original
held samples cannot tune either clock. No gate is revised and no DS11 fit follows.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from fragment_model import predict
from model import wrap

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    cp=HERE/'calibration.json';sp=HERE/'summary.json'
    cal=json.loads(cp.read_text());summary=json.loads(sp.read_text())
    sources={str(p):digest(p) for p in (cp,sp,Path(__file__),HERE/'model.py',HERE/'fragment_model.py')}
    results=[]
    for state in (cal,summary['validation']):
        index=state['index'];path=HERE.parent/f'frame_evolution/input-{index:02d}.json'
        doc=json.loads(path.read_text());sources[str(path)]=digest(path)
        for p,h in doc['sources'].items():assert digest(p)==h,p
        fits={(r['norad'],r['rf_hz']):r for r in state['rows'] if r['qualified']}
        owners=defaultdict(set)
        for row in doc['rows']:
            for p in row['points']:owners[p['candidate_id']].add((row['norad'],row['rf_hz']))
        matched=defaultdict(dict);track_results=[]
        for row in sorted(doc['rows'],key=lambda r:hashlib.sha256(r['track_id'].encode()).digest()):
            key=(row['norad'],row['rf_hz'])
            if key not in fits:continue
            source=fits[key]
            points=list({p['candidate_id']:p for p in row['points'] if len(owners[p['candidate_id']])==1}.values())
            t=np.array([p['frame_time_s'] for p in points]);phase=np.array([p['phase_us'] for p in points])
            original=np.array([p['training'] for p in points],bool)
            train=original & (t<=source['boundary_s']);held=~original & (t>source['boundary_s'])
            fit=predict(t,phase,train,held,doc['frame_period_us'])
            track_results.append(dict(track_id=row['track_id'],norad=key[0],rf_hz=key[1],**fit))
            if not fit['qualified']:continue
            u=(t[held]-source['center_s'])/source['scale_s']
            x=np.column_stack((np.ones(len(u)),u,u*u))
            errors=wrap(phase[held]-x@source['coefficients'],doc['frame_period_us'])
            for point,e,f in zip(np.array(points,dtype=object)[held],errors,fit['errors_us']):
                matched[key].setdefault(point['candidate_id'],(float(e),f))
        groups=[]
        for key,values in sorted(matched.items()):
            a=np.array(list(values.values()))
            groups.append(dict(norad=key[0],rf_hz=key[1],matched_points=len(a),
                               source_median_us=float(np.median(abs(a[:,0]))),
                               fragment_median_us=float(np.median(abs(a[:,1]))),
                               source_hit_fraction=float(np.mean(abs(a[:,0])<=cal['threshold_us'])),
                               fragment_hit_fraction=float(np.mean(abs(a[:,1])<=cal['threshold_us']))))
        result=dict(index=index,groups=groups,track_fits=track_results,
                    matched_groups=len(groups),total_qualified_source_groups=len(fits),
                    qualified_fragment_fits=sum(r['qualified'] for r in track_results),
                    fragment_wins=sum(r['fragment_median_us']<r['source_median_us'] for r in groups),
                    median_source_error_us=float(np.median([r['source_median_us'] for r in groups])),
                    median_fragment_error_us=float(np.median([r['fragment_median_us'] for r in groups])),
                    median_source_hit=float(np.median([r['source_hit_fraction'] for r in groups])),
                    median_fragment_hit=float(np.median([r['fragment_hit_fraction'] for r in groups])))
        results.append(result)
    out=dict(recordings=results,sources=sources,diagnostic_only=True,causal_position_improvement_established=False)
    with (HERE/'fragment-diagnostic.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('groups','track_fits')} for r in results],indent=2))


if __name__=='__main__':main()
