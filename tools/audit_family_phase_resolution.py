"""Audit local phase-integral values and gradients at saved recovery endpoints."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily,resolution_audit


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.input/'protocol.json');trial=read(args.input/'new_family.json')
    inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv)
    step=pr['phase_step_s'];family=NewFamily(d['scan'],pr['targets'],d['model'],phase_step=step,allow_uncalibrated_label=True);results={}
    for arm,row in trial['arms'].items():
        x=np.array(row['endpoint_east_north_km']);kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(row['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,d['entries'],d['powers']);cached(p)
        audit=resolution_audit(family,p,x,d['powers'],d['entries'],d['model'])
        if 'scores' not in audit:raise ValueError(audit['reason'])
        if not np.isclose(audit['scores'][0,0],row['family']['negative_twice_log_density'],atol=1e-5,rtol=0):raise ValueError('source target likelihood did not replay')
        results[arm]=dict(x=x,**audit)
    write(args.output/'result.json',dict(job=pr['job'],source=str(args.input),arms=results,position_refitted=False,
        incumbent_phase_reference_fixed_locally=True,GPS_used=False,not_a_statistical_confidence_interval=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['study','input','output']:p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
