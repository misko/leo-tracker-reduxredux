"""Compare finalists using only independently calibrated family predictions."""
import argparse
from pathlib import Path
import numpy as np
from investigate import read,write,context,published,ARMS,scalar_noise,profile_rate,family_frequency,corrected_observation


def main(out,case):
    rows=[r for r in read(out/'targets.json') if r['case']==case];d=context(read(rows[0]['inventory_path']));owners,public=published(case);scan=d['scan'];results=[]
    for row in rows:
        source=read(out/'cases'/case/(row['fragment_id']+'.json'));i=row['track_index'];tr=scan.tracks[i];idx=np.asarray(row['source_local_indices']);t=tr['times'][idx]
        fits=[r for r in source['fits'] if r['regime']=='causal' and r['model']=='phase_small_rate']
        choices=sorted({r['norad'] for a in ARMS for r in sorted([r for r in fits if r['arm']==a],key=lambda r:r['cost'])[:3]})
        pairs=[]
        for a in ARMS:
            p,_=d['problems'][a];x=np.asarray(public[a]['endpoint_east_north_km']);raw=corrected_observation(p,x,i)[idx]
            if i in p.members:assert not p.keep[p.slices[p.members.index(i)]][idx].any()
            for n in choices:
                j=int(np.flatnonzero(scan.norads==n)[0]);support=[(scan.tracks[k]['key'],int(p.keep[sl].sum())) for k,sl,r in zip(p.members,p.slices,p.rows) if r['candidate_norad']==n and p.keep[sl].any() and k!=i]
                if not support:pairs.append(dict(arm=a,norad=n,status='no_independent_calibrated_family'));continue
                f,e=family_frequency(p,x,j,times=t);v=profile_rate(raw,tr['rf_hz']/11.5e9*f,t,bias_sigma_hz=300.)
                noise=scalar_noise(v['residual_hz'][0],t)
                pairs.append(dict(arm=a,norad=n,status='independent_shared_prediction',support=support,phase_s=float(p.state(x)['phases'][j]),rms_hz=float(v['rms_hz'][0]),offset_hz=float(v['bias_hz'][0]),score=float(v['cost'][0]),noise=noise,minimum_elevation_deg=float(e.min()),prediction_hz=tr['rf_hz']/11.5e9*f,residual_hz=v['residual_hz'][0]))
        results.append(dict(source=row,predictions=pairs,policy='original shared satellite phase and physical orbital modes and receiver calibration, reconditioned at published endpoint; target excluded; 300Hz target bias marginalized/profiled, no target rate or phase fit'))
    write(out/'cases'/case/'shared_competitors.json',results)
    print(case,'shared competitors complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('case');a=p.parse_args();main(a.output,a.case)
