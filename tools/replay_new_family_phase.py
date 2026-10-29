"""Refine a diagnostic phase mode without changing the saved position fit."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.trial/'protocol.json');trial=read(args.trial/'new_family.json')
    inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv)
    family=NewFamily(d['scan'],pr['targets'],d['model'],phase_step=pr['phase_step_s']);rows={}
    for arm,v in trial['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(v['endpoint_east_north_km'])
        grid=family.evaluate(p,x,d['powers'],d['entries'],details=True)
        if not np.isclose(grid['negative_twice_log_density'],v['family']['negative_twice_log_density'],atol=1e-6,rtol=0):raise ValueError('saved likelihood replay mismatch')
        refined=family.evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True)
        rows[arm]=dict(grid=grid,continuous=refined)
        print(arm,refined['phase_map_s'],[(r['profile_RMS_hz'],r['noise']) for r in refined['diagnostics']],flush=True)
    write(args.output/'result.json',dict(job=pr['job'],arms=rows,position_changed=False,likelihood_changed=False,acceptance_unchanged=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['study','trial','output']:p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
