"""Replay unchanged residual/visibility/owner gates with explicit failure reasons."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from leo.analysis.research.retained_track_likelihood import profile,whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.orbital_support import requires_multiple_orbital_owners


def explain(p,x,saved):
    state=p.state(x);calc=p.calculate(x);frequency,elevation=p.conditional_frequency(x);rows=[];owners={}
    expected={r['component']:r for r in saved['gates']['tracks']}
    for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        use=p.keep[sl]
        if not use.any():continue
        t=p.scan.tracks[i];q=t['rf_hz']/11.5e9;times=t['times'][use]
        y=t['values']-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms=profile(y[use],q*frequency[sl][use],*whitening(times));noise=batch_noise_screen(terms['innovations'],times)
        gate=expected[t['key']];checks=dict(profile_RMS=bool(terms['rms'][0]<=450),profile_bias=bool(abs(terms['bias'][0])<=3000),
            profile_noise=bool(noise['noise_screen_pass'][0]),conditional_noise=bool(gate['conditional_residual_gate']['compatible']),
            alias=bool(int(terms['alias'][0])==alias),visibility=bool(elevation[sl][use].min()>=0))
        if all(checks.values()):owners.setdefault(row['candidate_index'],set()).add((t['receiver'],t['channel']))
        rows.append(dict(component=t['key'],norad=row['candidate_norad'],candidate_index=row['candidate_index'],receiver=t['receiver'],channel=t['channel'],
            points=int(use.sum()),checks=checks,conditional=gate['conditional_residual_gate'],
            profile_noise={k:bool(v[0]) if v.dtype==bool else float(v[0]) for k,v in noise.items()},
            profile_RMS_hz=float(terms['rms'][0]),profile_bias_hz=float(terms['bias'][0]),minimum_elevation_deg=float(elevation[sl][use].min()),
            times_s=times,residual_hz=calc['conditional_residual_hz'][sl][use],rf_hz=t['rf_hz']))
    for row in rows:
        j=row['candidate_index'];count=len(owners.get(j,()));required=requires_multiple_orbital_owners(p,j)
        row.update(pre_gate_passing_owners=count,multiple_owners_required=required)
        row['checks']['owner_support']=not required or count>=2
        row['failure_reasons']=[k for k,v in row['checks'].items() if not v]
        row['compatible']=all(row['checks'].values())
        if row['compatible']!=expected[row['component']]['compatible']:raise ValueError('gate replay disagrees with original')
    return rows


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.input/'protocol.json');inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json')
    d=context(inv);base,_=d['problems']['c0'];results={}
    for path in sorted(args.input.glob('*.json')):
        r=read(path)
        if 'arms' not in r:continue
        node,keep=configuration(d['node'],d['keep'],base.slices,r['target_entries']);means,_=prior_means(d,node);pair={}
        for arm,saved in r['arms'].items():
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            p=make_event_problem(d['scan'],node,keep,arm,np.array(saved['phase_reference']),d['powers'],means,d['model'],[],**kw)
            attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(saved['endpoint_east_north_km'])
            delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta)>1e-5:raise ValueError('objective replay differs')
            pair[arm]=dict(objective_replay_difference=delta,tracks=explain(p,x,saved))
        results[path.stem]=pair
    write(args.output/'result.json',dict(job=pr['job'],source=str(args.input),variants=results,no_gate_changes=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['study','input','output']:p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
