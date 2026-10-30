"""Exact shared-phase feasibility slices at frozen RF-only endpoints.

This is an in-sample diagnostic, not an association or localization method.
Receiver and orbit coefficients, position, identity, alias and observations are
fixed. Only one satellite phase and its existing curve constants can change.
"""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context, validated_native_source
from ds23_frequency_events import make_event_problem, attach_event_predictive
from conditional_satellite_refresh import attach_conditional_satellite_refresh
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from investigate_ds23_0268_remaining_tracks import family_frequency
from ds23_feasible_position import noise_slacks, residual_slacks
from probe_algo03_feasible_recovery import gate_slacks
from leo.analysis.research.retained_track_likelihood import profile, whitening


def fixed_alias_constant(raw, weight, prior_precision):
    """Conditional MAP constant with fixed positive precisions; no alias search."""
    y, w = np.asarray(raw, float), np.asarray(weight, float)
    if y.ndim != 1 or y.shape != w.shape or not len(y):
        raise ValueError('matching nonempty observation and precision vectors required')
    if not np.isfinite(y).all() or not np.isfinite(w).all() or np.any(w <= 0):
        raise ValueError('finite observations and positive precision required')
    if not np.isfinite(prior_precision) or prior_precision <= 0:
        raise ValueError('positive finite constant prior precision required')
    bias = float(w @ y / (w.sum() + prior_precision))
    residual = y - bias
    return dict(bias_hz=bias, residual_hz=residual,
                cost=float(w @ (residual * residual) + prior_precision * bias * bias))


def sampled_intervals(grid, accepted):
    """Return sampled support runs, never interpolate feasibility across holes."""
    x, ok = np.asarray(grid, float), np.asarray(accepted, bool)
    if x.ndim != 1 or x.shape != ok.shape or not np.isfinite(x).all() or np.any(np.diff(x) <= 0):
        raise ValueError('strictly increasing finite grid and matching mask required')
    starts = np.flatnonzero(ok & ~np.r_[False, ok[:-1]])
    ends = np.flatnonzero(ok & ~np.r_[ok[1:], False])
    return [[float(x[a]), float(x[b]), int(b-a+1)] for a,b in zip(starts, ends, strict=True)]


def constant_scale(p, k):
    """Respect prior-guard scaling of a fragment's existing constant column."""
    values=np.asarray(p.constants[p.slices[k],k],float)
    if not len(values) or not np.isfinite(values).all() or values[0]<=0 or not np.all(values==values[0]):
        raise ValueError('one positive constant column scale per fragment required')
    return float(values[0])


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    protocol=read(args.diagnostic/'protocol.json');inv=read(Path(protocol['inventory']))
    source=validated_native_source(Path(protocol['validation']));d=context(inv)
    target=protocol['target'];bid=target['component'].split('-NATIVE-')[-1]
    d,_=native_context(d,inv,source,bid);j=target['candidate_index']
    entries=d['entries']+[target];answers={}
    write(out/'protocol.json',dict(source_diagnostic=str(args.diagnostic),source_protocol=protocol,
        endpoints=[str(p) for p in args.endpoints],position_fixed=True,receiver_fixed=True,
        orbit_coefficients_fixed=True,shared_phase_only=True,original_aliases_fixed=True,
        existing_constant_priors=True,matched_c=True,GPS_used=False,future_TLE=False,
        phase_grid='[-15,15] step .1s plus +/-1s around endpoint phase step .002s',
        score='conditional weighted MAP at frozen Gamma precision; predictive variance 2*sigma^2 and 300 Hz bias; not marginal ELBO',
        in_sample_only=True,no_accepted_associations=True))
    for endpoint in args.endpoints:
        saved=read(endpoint/'target_0.json');ep=read(endpoint/'protocol.json');name=endpoint.name
        answers[name]={}
        for arm,row in saved['arms'].items():
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(row['phase_reference']),
                d['powers'],d['means'],d['model'],[],**kw)
            attach_event_predictive(p,entries,d['powers'])
            if ep.get('conditional_satellite_refresh'):
                attach_conditional_satellite_refresh(p,entries,d['powers'],[j])
            x=np.array(row['endpoint_east_north_km']);c=p.calculate(x)
            replay=c['negative_twice_elbo']-row['negative_twice_elbo']
            if abs(replay)>1e-5:raise ValueError('endpoint objective failed replay')
            original_calculate=p.calculate;original_frequency=p.conditional_frequency
            original_f,original_e=original_frequency(x)
            begin=p.hardware.shape[1]+p.smooth.shape[1];local=p.labels.index(j)
            phase_index=begin+local;constant_start=begin+len(p.labels)+3*len(p.supported)
            initial_phase=float(c['coefficient'][phase_index]*p.phase_sigma[local])
            view,values,sigma,_,slices=linear_geometry(p,entries);geo=geometry_features(view,x,0.)
            hardware=geo['features'][:,:begin]@c['coefficient'][:begin]
            curves=[]
            for k,(r,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                active=p.keep[sl]
                if r['candidate_index']!=j or not active.any():continue
                t=p.scan.tracks[i];weight=d['powers'][k]*c['noise_precision'][k]/p.point_noise[sl][active]**2
                curves.append(dict(component=t['key'],kind='curved',track_index=i,slot=k,
                    times_s=t['times'][active],q=t['rf_hz']/11.5e9,
                    raw=p.values[sl][active]-(c['features'][sl,:begin]@c['coefficient'][:begin])[active],
                    weight=weight,constant_scale_hz=constant_scale(p,k),
                    prior_precision=float(c['coefficient_prior_precision'][constant_start+k]/constant_scale(p,k)**2),
                    receiver=t['receiver'],channel=t['channel'],points=int(active.sum())))
            for k,(e,sl) in enumerate(zip(entries,slices,strict=True)):
                if e['candidate_index']!=j:continue
                t=p.scan.tracks[e['track_index']]
                curves.append(dict(component=e['component'],kind='target' if e is target else 'predictive',
                    track_index=e['track_index'],slot=k,times_s=t['times'],q=t['rf_hz']/11.5e9,
                    raw=values[sl]-hardware[sl],receiver=t['receiver'],channel=t['channel'],points=len(t['times'])))
                curves[-1].update(weight=1/(2*sigma[sl]**2),prior_precision=1/300.**2)
            initial_coef=c['coefficient'].copy()
            def evaluate(phase, full=False):
                coefficient=initial_coef.copy();coefficient[phase_index]=phase/p.phase_sigma[local]
                cc=dict(c,coefficient=coefficient);p.calculate=lambda _:cc
                score=float(c['coefficient_prior_precision'][phase_index]*(coefficient[phase_index]-d['means'][local]/p.phase_sigma[local])**2)
                records=[];frequency=original_f.copy();elevations=original_e.copy()
                conditional=c['conditional_residual_hz'].copy();linear=c['linear_raw_prediction_residual_hz'].copy();le=c['linear_elevation'].copy()
                try:
                    for curve in curves:
                        f,e=family_frequency(p,x,j,times=curve['times_s']);raw=curve['raw']-curve['q']*f
                        terms=profile(raw,np.zeros(len(raw)),*whitening(curve['times_s']),
                            bias_sigma=1000. if curve['kind']=='curved' else 300.)
                        gates=dict(rms=1-float(terms['rms'][0])/450,bias=1-abs(float(terms['bias'][0]))/3000,
                            alias=.5-abs(float(terms['alias'][0])),elevation=float(e.min())/10,
                            **noise_slacks(terms['innovations'][0],curve['times_s']))
                        if curve['kind']=='curved':
                            v=fixed_alias_constant(raw,curve['weight'],curve['prior_precision']);score+=v['cost']
                            gates.update({'conditional_'+k:v for k,v in residual_slacks(v['residual_hz'],curve['times_s']).items()})
                            k=curve['slot'];sl=p.slices[k];active=p.keep[sl]
                            coefficient[constant_start+k]=v['bias_hz']/curve['constant_scale_hz']
                            conditional[sl][active]=v['residual_hz'];frequency[sl][active]=f;elevations[sl][active]=e
                        else:
                            score+=fixed_alias_constant(raw,curve['weight'],curve['prior_precision'])['cost']
                            sl=slices[curve['slot']];linear[sl]=raw;le[sl]=e
                            v=dict(bias_hz=float(terms['bias'][0]),residual_hz=terms['residual'][0])
                        records.append(dict(component=curve['component'],kind=curve['kind'],gates=gates,
                            minimum_slack=min(gates.values()),bias_hz=v['bias_hz'],
                            RMS_hz=float(np.sqrt(np.mean(v['residual_hz']**2))),residual_hz=v['residual_hz']))
                    result=dict(phase_s=float(phase),score=score,curves=records,minimum_family_slack=min(r['minimum_slack'] for r in records))
                    if full:
                        cc.update(conditional_residual_hz=conditional,linear_raw_prediction_residual_hz=linear,linear_elevation=le)
                        p.conditional_frequency=lambda _: (frequency,elevations)
                        gates=gate_slacks(p,x,entries)
                        result.update(all_gate_slacks=gates,minimum_all_slack=min(gates.values()),
                            receiver_coefficient_change=float(np.max(abs(coefficient[:begin]-initial_coef[:begin]))))
                    return result
                finally:p.calculate=original_calculate;p.conditional_frequency=original_frequency
            grid=np.unique(np.round(np.r_[np.arange(-15,15.0001,.1),initial_phase+np.arange(-1,1.0001,.002),initial_phase],10))
            grid=grid[(grid>=-15)&(grid<=15)];rows=[evaluate(v) for v in grid]
            minimum=np.array([r['minimum_family_slack'] for r in rows]);scores=np.array([r['score'] for r in rows]);ok=minimum>=0
            selected=int(np.flatnonzero(ok)[np.argmin(scores[ok])]) if ok.any() else int(np.argmax(minimum))
            summary=dict(initial=evaluate(initial_phase,True),selected=evaluate(grid[selected],True),
                unconstrained=evaluate(grid[np.argmin(scores)],True),
                sampled_joint_intervals=sampled_intervals(grid,ok),sampled_feasible_points=int(ok.sum()),
                endpoint_east_north_km=x,objective_replay_difference=replay,
                curves=[{k:v for k,v in curve.items() if k not in ('weight','raw')} for curve in curves],
                grid_phase_s=grid,grid_score=scores,grid_minimum_family_slack=minimum,
                curve_grid=[dict(component=curve['component'],kind=curve['kind'],
                    RMS_hz=[r['curves'][k]['RMS_hz'] for r in rows],
                    minimum_slack=[r['curves'][k]['minimum_slack'] for r in rows],
                    sampled_intervals=sampled_intervals(grid,[r['curves'][k]['minimum_slack']>=0 for r in rows]))
                    for k,curve in enumerate(curves)])
            answers[name][arm]=summary
            write(out/(name+'-'+arm+'.json'),summary)
            print(name,arm,'phase',initial_phase,'feasible samples',int(ok.sum()),'best full slack',summary['selected']['minimum_all_slack'],flush=True)
    write(out/'result.json',dict(job=inv['job'],target=target,endpoints=answers,diagnostic_only=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnostic',type=Path,required=True);p.add_argument('--endpoints',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
