"""Expose support selection in the matched fragment-clock diagnostic."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from model import wrap

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    paths=[HERE/n for n in ('calibration.json','summary.json','fragment-diagnostic.json')]
    cal,summary,diagnostic=[json.loads(p.read_text()) for p in paths]
    sources={str(p):digest(p) for p in paths+[Path(__file__),HERE/'model.py']}
    recordings=[]
    for state,diag in zip((cal,summary['validation']),diagnostic['recordings']):
        path=HERE.parent/f"frame_evolution/input-{state['index']:02d}.json"
        doc=json.loads(path.read_text());sources[str(path)]=digest(path)
        qualified={r['track_id'] for r in diag['track_fits'] if r['qualified']}
        fits={(r['norad'],r['rf_hz']):r for r in state['rows'] if r['qualified']}
        owners=defaultdict(set);groups=defaultdict(dict);supported=set()
        for track in doc['rows']:
            key=(track['norad'],track['rf_hz'])
            for point in track['points']:
                cid=point['candidate_id'];owners[cid].add(key);groups[key][cid]=point
                if track['track_id'] in qualified:supported.add(cid)
        rows=[];all_values=[]
        for key,fit in fits.items():
            points=[p for cid,p in groups[key].items() if len(owners[cid])==1 and not p['training'] and p['frame_time_s']>fit['boundary_s']]
            t=np.array([p['frame_time_s'] for p in points]);u=(t-fit['center_s'])/fit['scale_s']
            error=abs(wrap(np.array([p['phase_us'] for p in points])-np.column_stack((np.ones(len(t)),u,u*u))@fit['coefficients'],doc['frame_period_us']))
            mask=np.array([p['candidate_id'] in supported for p in points])
            assert len(error)==fit['held_points']
            values=np.column_stack((error,mask,t-fit['boundary_s']));all_values.extend(values.tolist())
            rows.append(dict(norad=key[0],rf_hz=key[1],held=len(points),matched=int(mask.sum()),
                             unmatched_median_us=float(np.median(error[~mask])) if (~mask).any() else None))
        assert sum(r['matched'] for r in rows)==sum(r['matched_points'] for r in diag['groups'])
        values=np.array(all_values);strata={}
        for name,mask in [('matched',values[:,1]==1),('unmatched',values[:,1]==0)]:
            a=values[mask]
            strata[name]=dict(points=len(a),median_error_us=float(np.median(a[:,0])) if len(a) else None,
                              hit_fraction=float(np.mean(a[:,0]<=cal['threshold_us'])) if len(a) else None,
                              median_time_after_boundary_s=float(np.median(a[:,2])) if len(a) else None)
        recordings.append(dict(index=state['index'],groups=rows,strata=strata))
    out=dict(recordings=recordings,sources=sources,diagnostic_only=True)
    with (HERE/'fragment-coverage.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps([dict(index=r['index'],strata=r['strata']) for r in recordings],indent=2))


if __name__=='__main__':main()
