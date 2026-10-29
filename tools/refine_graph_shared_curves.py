"""Check nearby gate-feasible solutions without changing the RF model."""

import argparse
from functools import partial
from pathlib import Path
import signal
import time
import numpy as np

import debug_fast_graph_unassociated as report
from probe_graph_shared_high_channels import context, receiver_basis, select_targets, inventory, figures


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    d=context(args);saved=report.read(args.trial);targets=select_targets(d)
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_frequency_events import cached,summary
    from probe_ds23_history_calibrated_phase import make_problem
    from ds23_feasible_position import feasible_fit
    from probe_algo03_feasible_recovery import gate_slacks
    from algo02_scan import pair_passes
    scan,node=receiver_basis(d['scan'],saved['node'],saved['basis'])
    keep=np.asarray(saved['mask'],bool);means=np.asarray(saved['means']);pair={}
    started=time.monotonic()
    def limit(*_):raise TimeoutError('180 s per-arm bound on feasible refinement')
    signal.signal(signal.SIGALRM,limit)
    for arm in ('c0','fitted_c'):
        signal.alarm(180)
        previous=saved['arms'][arm]
        x=np.asarray(previous['endpoint_east_north_km']);reference=np.asarray(previous['phase_reference']);history=[]
        for epoch in range(5):
            p=make_event_problem(scan,node,keep,arm,reference,d['powers'],means,d['model'],saved['events'],
                base_problem_factory=partial(make_problem,support_policy='active'))
            attach_event_predictive(p,d['entries'],d['powers']);cached(p)
            if epoch==0:
                assert abs(p.calculate(x)['negative_twice_elbo']-previous['negative_twice_elbo'])<1e-5
            initial=min(gate_slacks(p,x,d['entries']).values())
            fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:np.asarray(list(gate_slacks(p,z,d['entries']).values()))-.01,
                x,p.lower,p.upper,iterations=30)
            x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference))),initial_slack=initial))
            reference=phase
            print(arm,epoch,'feasible',fitted['feasible'],'min slack',fitted['minimum_gate_slack'],'phase',history[-1]['phase_change_s'],flush=True)
        r=summary(p,x,d['entries']);c=p.calculate(x)
        curved,predictive,associated,_=report.memberships(p,x,d['entries'])
        r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
            objective_cost_from_unconstrained=r['negative_twice_elbo']-previous['negative_twice_elbo'],
            minimum_gate_slack=min(gate_slacks(p,x,d['entries']).values()),
            curved_points=len(curved),predictive_points=len(predictive),raw_associated_points=len(associated),
            raw_associated_ids=sorted(associated),postfit_only_points=len(associated-curved-predictive),
            targets=[dict(gate=next(g for g in r['gates']['tracks'] if g['component']==p.rows[k]['component']),
                times_s=scan.tracks[p.members[k]]['times'],values_hz=scan.tracks[p.members[k]]['values'],
                conditional_residual_hz=c['conditional_residual_hz'][p.slices[k]]) for k in targets])
        pair[arm]=r;report.write(out/(arm+'.json'),r);signal.alarm(0)
    result=dict(saved,arms=pair,paired_valid=pair_passes(pair,include_linear=True),
        constrained_refinement=True,unchanged_model_and_original_gates=True,interior_margin=.01,
        source_trial=str(args.trial),seconds=time.monotonic()-started)
    report.write(out/'result.json',result)
    figures(out,inventory(d,targets),dict(unconstrained=saved,feasible=result))
    print('Qualified',result['paired_valid'],[(a,r['raw_associated_points'],r['objective_cost_from_unconstrained'],r['endpoint_east_north_km']) for a,r in pair.items()],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('run','source-root','ch1','trial','output'):parser.add_argument('--'+name,required=True,type=Path)
    run(parser.parse_args())
