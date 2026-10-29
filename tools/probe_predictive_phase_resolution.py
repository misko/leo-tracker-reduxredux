"""Matched phase-quadrature resolution along a saved position-displacement line."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.input/'protocol.json')
    inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv)
    control=read(args.input/'control.json');trial=read(args.input/'new_family.json')
    steps=[.1,.05,.025,.0125];families={h:NewFamily(d['scan'],pr['targets'],d['model'],phase_step=h,allow_uncalibrated_label=True) for h in steps}
    write(args.output/'protocol.json',dict(source=str(args.input),job=pr['job'],steps_s=steps,line_fraction=np.linspace(-.25,1.25,25),
        five_phase_refreshes_at_each_fixed_position=True,position_not_optimized=True,GPS_used=False))
    results={}
    for arm in ('c0','fitted_c'):
        start=np.array(control['arms'][arm]['endpoint_east_north_km']);end=np.array(trial['arms'][arm]['endpoint_east_north_km']);rows=[]
        for u in np.linspace(-.25,1.25,25):
            x=start+u*(end-start);reference=np.zeros(len(d['means']))
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                change=float(np.max(abs(phase-reference)));reference=phase
            c=p.calculate(x);old=c['negative_twice_elbo']+float(np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4);scores=[]
            for step,f in families.items():
                detail=f.evaluate(p,x,d['powers'],d['entries'],details=True)
                scores.append(dict(step_s=step,target_score=detail['negative_twice_log_density'],total_score=old+detail['negative_twice_log_density'],
                    phase_mean_s=detail['phase_mean_s'],phase_sigma_s=detail['phase_sigma_s'],phase_map_s=detail['phase_map_s']))
            rows.append(dict(fraction=float(u),x=x,incumbent_score=old,final_phase_change_s=change,scores=scores))
        results[arm]=dict(start=start,end=end,displacement_km=float(np.linalg.norm(end-start)),rows=rows)
        write(args.output/(arm+'.json'),results[arm]);print(arm,'complete',flush=True)
    write(args.output/'result.json',dict(job=pr['job'],arms=results,source=str(args.input)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['study','input','output']:p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
