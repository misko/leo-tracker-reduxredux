"""Exact incumbent/control replay and local gate-boundary diagnostic, without GPS."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read, write, memberships
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations


def run(args):
    inv = read(args.inventory); control = read(args.control); d = context(inv)
    result = dict(inventory=str(args.inventory), control=str(args.control), arms={},
                  GPS_used=False, no_refit=True, line_phase_reference='frozen incumbent')
    for arm, old in inv['policy'].items():
        rows = {}; problems = {}
        for name, saved in [('frozen', old), ('control', control['arms'][arm])]:
            kw = {'base_problem_factory': d['problem_factory']} if 'problem_factory' in d else {}
            p = make_event_problem(d['scan'], d['node'], d['keep'], arm,
                np.array(saved['phase_reference']), d['powers'], d['means'], d['model'], [], **kw)
            attach_event_predictive(p, d['entries'], d['powers']); cached(p)
            x = np.array(saved['endpoint_east_north_km']); calc = p.calculate(x)
            delta = calc['negative_twice_elbo'] - saved['negative_twice_elbo']
            if abs(delta) > 1e-5: raise ValueError(f'{arm} {name} replay differs: {delta}')
            gates = retained_metrics(p, x)
            if gates != saved['gates']:  # compare numerical fields with tolerance below
                bykey = {g['component']: g for g in saved['gates']['tracks']}
                for g in gates['tracks']:
                    previous = bykey[g['component']]
                    if g['compatible'] != previous['compatible']: raise ValueError('gate classification differs')
                    if abs(g['profile_rms_hz']-previous['profile_rms_hz']) > 1e-5: raise ValueError('gate RMS differs')
            _, _, ids, owners = memberships(p, x, d['entries'])
            if ids != set(saved['proposed_associated_ids']): raise ValueError('memberships differ')
            tracks = []
            for r, i, sl in zip(p.rows, p.members, p.slices, strict=True):
                t = p.scan.tracks[i]; active = p.keep[sl]
                if not active.any(): continue
                tracks.append(dict(component=t['key'], norad=r['candidate_norad'],
                    times_s=t['times'][active], CFO_hz=t['values'][active],
                    residual_hz=calc['conditional_residual_hz'][sl][active], pieces=t['pieces'],
                    gate=next(g for g in gates['tracks'] if g['component']==t['key'])))
            rows[name] = dict(endpoint=x, objective=calc['negative_twice_elbo'],
                objective_replay_difference=delta, tracks=tracks, owners=owners,
                associated_ids=sorted(ids), extensions=extend_associations(p,x,gates)['tracks'])
            problems[name] = p,x
        lost = set(rows['frozen']['associated_ids'])-set(rows['control']['associated_ids'])
        lost_tracks=[]
        for t in d['scan'].tracks:
            selected=set(t['observation_ids'])&lost
            if selected:
                lost_tracks.append(dict(component=t['key'], points=len(selected), receiver=t['receiver'],
                    channel=t['channel'], times_s=t['times'], CFO_hz=t['values'],
                    frozen_satellites=sorted({rows['frozen']['owners'][o] for o in selected})))
        p, start=problems['frozen'];end=problems['control'][1];line=[]
        # A one-dimensional slice with the incumbent phase linearization;
        # nuisance coefficients reprofile at each position. This is not a
        # complete pipeline rerun or a fully phase-refreshed loss surface.
        for fraction in np.linspace(0,1.25,26):
            x=start+fraction*(end-start);m=retained_metrics(p,x)
            line.append(dict(fraction=fraction, displacement_m=float(np.linalg.norm(x-start)*1000),
                objective=p.calculate(x)['negative_twice_elbo'],
                tracks=[dict(component=g['component'], compatible=g['compatible'],
                    step_z=g['conditional_residual_gate']['diagnostics']['maximum_step_z']) for g in m['tracks']]))
        result['arms'][arm]=dict(replays=rows, lost_tracks=lost_tracks, lost_points=len(lost), line=line,
            endpoint_shift_m=float(np.linalg.norm(end-start)*1000))
    write(args.output,result)
    print({a:dict(shift_m=r['endpoint_shift_m'],lost=r['lost_points'],tracks=[(t['component'],t['points'],t['frozen_satellites']) for t in r['lost_tracks']]) for a,r in result['arms'].items()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('inventory','control','output'):p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
