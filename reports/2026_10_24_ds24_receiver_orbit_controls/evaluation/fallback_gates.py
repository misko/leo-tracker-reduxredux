"""RF-only failure attribution at saved endpoints; never relax gates or refit."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import csv
from pathlib import Path
import numpy as np

from matched_controls import HERE,digest,load_adapter,load_baseline,load_protocol,read,write


def screen_failures(prefix,diagnostics,n):
    limits={'mean_z':3.,'slope_z':3.,'quadratic_bic_gain':10.,'maximum_step_z':4.,'lag1_acf':4/np.sqrt(n)}
    rows=[]
    for metric,limit in limits.items():
        raw=float(diagnostics[metric]);value=abs(raw) if metric=='lag1_acf' else raw
        if value>limit:rows.append(dict(criterion=prefix+'_'+metric,value=raw,threshold=float(limit),excess=float(value-limit)))
    return rows


def limit_failure(name,value,threshold,absolute=False):
    observed=abs(value) if absolute else value
    return [dict(criterion=name,value=float(value),threshold=float(threshold),excess=float(observed-threshold))] if observed>threshold else []


def one(args):
    protocol_path,case=args
    from leo.analysis.research.retained_track_likelihood import profile,whitening
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    protocol,_=load_protocol(protocol_path)
    path=HERE/'models'/protocol['model_id']/(case+'.json');saved=read(path)
    d=load_baseline(case);module=load_adapter(protocol['adapter']['path']);arms={}
    for arm,r in saved['arms'].items():
        phase_fail=limit_failure('phase_reference_change_s',r['final_phase_change_s'],.01)
        phase_fail+=limit_failure('absolute_phase_s',float(np.max(abs(np.asarray(r['state']['phases'])))),15.000001)
        p=module.build(d,arm,np.asarray(r['phase_reference']),case);x=np.asarray(r['endpoint_east_north_km'])
        state=p.state(x);c=p.calculate(x);frequency,elevation=p.conditional_frequency(x)
        by_key={g['component']:g for g in r['gates']['tracks']};curved=[]
        for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
            t=p.scan.tracks[i];use=p.keep[sl]
            if not use.any() or by_key[t['key']]['compatible']:continue
            times=t['times'][use];n=len(times);q=t['rf_hz']/11.5e9
            raw=t['values']-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
            terms=profile(raw[use],q*frequency[sl][use],*whitening(times))
            noise=batch_noise_screen(terms['innovations'],times)
            original=by_key[t['key']];condition=original['conditional_residual_gate'];reasons=[]
            reasons+=limit_failure('profile_RMS_hz',float(terms['rms'][0]),450.)
            reasons+=limit_failure('profile_bias_hz',float(terms['bias'][0]),3000.,True)
            reasons+=screen_failures('profile', {k:v[0] for k,v in noise.items()},n)
            reasons+=limit_failure('conditional_RMS_hz',condition['rms_hz'],450.)
            reasons+=screen_failures('conditional',condition['diagnostics'],n)
            if int(terms['alias'][0])!=alias:reasons.append(dict(criterion='alias_change',value=int(terms['alias'][0]),threshold=int(alias),excess=None))
            minimum_elevation=float(elevation[sl][use].min())
            if minimum_elevation<0:reasons.append(dict(criterion='negative_elevation_deg',value=minimum_elevation,threshold=0.,excess=-minimum_elevation))
            direct_failed=bool(reasons)
            if not reasons:
                assert row['candidate_index'] in p.supported
                lookup={t['key']:t for t in p.scan.tracks}
                owners={(lookup[g['component']]['receiver'],lookup[g['component']]['channel']) for g in by_key.values()
                    if g['compatible'] and g['candidate_index']==row['candidate_index']}
                reasons.append(dict(criterion='two_owner_support_cascade',value=len(owners),threshold=2,excess=2-len(owners)))
            curved.append(dict(component=t['key'],norad=int(row['candidate_norad']),receiver=t['receiver'],channel=t['channel'],points=n,
                reasons=reasons,direct_residual_or_physical_failure=direct_failed,
                conditional_diagnostics=condition['diagnostics'],profile_diagnostics={k:v[0] for k,v in noise.items()}))
        linear=[]
        for entry,sl,gate in zip(d['entries'],getattr(p,'linear_slices',[]),r['linear_gates'],strict=True):
            if gate['compatible']:continue
            t=p.scan.tracks[entry['track_index']];residual=c['linear_raw_prediction_residual_hz'][sl]
            terms=profile(residual,np.zeros(len(residual)),*p.scan.white[entry['track_index']],bias_sigma=300.)
            noise=batch_noise_screen(terms['innovations'],t['times']);n=len(residual);reasons=[]
            reasons+=limit_failure('predictive_profile_RMS_hz',float(terms['rms'][0]),450.)
            reasons+=limit_failure('predictive_bias_hz',float(terms['bias'][0]),3000.,True)
            reasons+=screen_failures('predictive',{k:v[0] for k,v in noise.items()},n)
            if int(terms['alias'][0])!=0:reasons.append(dict(criterion='predictive_alias_change',value=int(terms['alias'][0]),threshold=0,excess=None))
            minimum=float(c['linear_elevation'][sl].min())
            if minimum<0:reasons.append(dict(criterion='predictive_negative_elevation_deg',value=minimum,threshold=0.,excess=-minimum))
            assert reasons
            linear.append(dict(component=t['key'],norad=entry['norad'],receiver=t['receiver'],channel=t['channel'],points=n,reasons=reasons))
        failed=bool(phase_fail or curved or linear)
        arms[arm]=dict(phase_failures=phase_fail,curved_failures=curved,predictive_failures=linear,
            failed=failed,final_phase_change_s=r['final_phase_change_s'])
    assert any(a['failed'] for a in arms.values())==(not saved['paired_valid'])
    return dict(model_id=protocol['model_id'],case=case,policy_source=saved['policy_source'],arms=arms,
        result_sha256=digest(path),GPS_used=False)


def main(protocols,workers):
    jobs=[]
    for path in protocols:
        protocol,_=load_protocol(path)
        for case in protocol['cases']:
            r=read(HERE/'models'/protocol['model_id']/(case+'.json'))
            if not r['paired_valid']:jobs.append((path,case))
    with ProcessPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(one,jobs))
    flat=[];model_summary={}
    for path in protocols:
        model=load_protocol(path)[0]['model_id'];group=[r for r in rows if r['model_id']==model]
        counts=Counter();arm_counts=Counter();phase_only=[];both=[]
        for r in group:
            phase=any(a['phase_failures'] for a in r['arms'].values())
            structure=any(a['curved_failures'] or a['predictive_failures'] for a in r['arms'].values())
            if phase and not structure:phase_only.append(r['case'])
            if phase and structure:both.append(r['case'])
            for arm,a in r['arms'].items():
                if a['failed']:arm_counts[arm]+=1
                items=[('phase','',f) for f in a['phase_failures']]
                for role,key in [('curved','curved_failures'),('predictive','predictive_failures')]:
                    items += [(role,g['component'],reason) for g in a[key] for reason in g['reasons']]
                for role,component,f in items:
                    counts[f['criterion']]+=1
                    flat.append(dict(model_id=model,case=r['case'],arm=arm,role=role,component=component,**f))
        model_summary[model]=dict(fallback_cases=len(group),failed_arm_counts=dict(arm_counts),criterion_occurrences=dict(counts),
            phase_only_cases=phase_only,phase_and_gate_cases=both,
            residual_or_physical_gate_cases=[r['case'] for r in group if any(a['curved_failures'] or a['predictive_failures'] for a in r['arms'].values())])
    write(HERE/'fallback_gate_breakdown.json',dict(rows=rows,summary=model_summary,
        no_refits_gate_relaxation_or_rescue=True,GPS_used=False,source_sha256=digest(Path(__file__))))
    with (HERE/'fallback_gate_failures.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['model_id','case','arm','role','component','criterion','value','threshold','excess'],lineterminator='\n');writer.writeheader();writer.writerows(flat)
    print(model_summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,action='append',required=True);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();assert 1<=a.workers<=4;main(a.protocol,a.workers)
