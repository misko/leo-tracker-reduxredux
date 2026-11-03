"""Gate-constrained refinement of frozen joint and matched-control hypotheses.

No new measurements, identities, noise scales or priors. Rejected endpoints
are eligible for bounded refinement only when every gate slack exceeds-.25.
Both c arms and the GLRT-only control receive the same refinement rule.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_feasible_position import feasible_fit,noise_slacks
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_joint_relative_position import OUT as SOURCE,CASES,context,make,relative_gates
from probe_ds23_frequency_events import cached,summary
from run_algo01_ds23_sample import read,write,sha
from run_ds23_combined_recovery_full import valid,ARMS

OUT=SOURCE/'feasible'
VARIANTS=[['quarantined_GLRT',False,float(np.sqrt(2)*300)],['joint_bias424',True,float(np.sqrt(2)*300)]]


def slacks(p,x,entries,bias_sigma):
    result=gate_slacks(p,x,entries);phase=p.state(x)['phases'][p.joint_all_labels]
    for k,value in enumerate(phase):result['phase/'+str(k)]=1-abs(float(value))/15
    if not p.relative_include:return result
    raw,elevation,_=p.exact_relative(x);c=p.calculate(x);rf=p.relative_problem
    if raw is None:raw=c['relative_residual_hz'];elevation=c['relative_elevation']
    coefficient=c['coefficient'][p.relative_mapping];begin=len(rf.labels)+3*len(rf.supported)
    for k,sl in enumerate(rf.slices):
        values=dict(rms=1-float(np.sqrt(np.mean(raw[sl]**2)))/450,
            bias=1-abs(float(bias_sigma*coefficient[begin+k]))/3000,
            elevation=float(elevation[sl].min())/10,**noise_slacks(raw[sl],rf.times[sl]))
        result.update({'relative/'+str(k)+'/'+key:value for key,value in values.items()})
    return result


def one(case,variant,include,bias_sigma,source,output):
    path=output/(case+'_'+variant+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s paired feasible joint cap')));signal.alarm(300)
    saved=read(source/(case+'_'+variant+'.json'))
    result=dict(saved,source_unconstrained_sha256=sha(source/(case+'_'+variant+'.json')))
    try:
        if saved['status']!='complete' or saved['accepted']:
            result.update(feasible_refinement_attempted=False,reason='already_accepted_or_no_qualified_inputs')
        else:
            d=context(case);minima=[]
            for arm in ARMS:
                r=saved['arms'][arm];p=make(d,arm,np.asarray(r['joint_phase_reference']),include,bias_sigma);cached(p)
                before=slacks(p,np.asarray(r['endpoint_east_north_km']),d['original_entries'],bias_sigma)
                minima.append(min(before.values()))
                passed=all(g['compatible'] for g in r['gates']['tracks']+r['linear_gates']+r['relative_gates']) and max(abs(np.asarray(r['state']['phases'])))<=15
                if passed!=(min(before.values())>=0):raise ValueError('constraint inequalities disagree with original residual gates')
            result['unconstrained_minimum_slacks']=minima
            if min(minima)<-.25:result.update(feasible_refinement_attempted=False,reason='outside_frozen_near_gate_refinement_budget')
            else:
                pair={}
                for arm in ARMS:
                    old=saved['arms'][arm];x=np.asarray(old['endpoint_east_north_km']);ref=np.asarray(old['joint_phase_reference']);history=[]
                    for _ in range(5):
                        p=make(d,arm,ref,include,bias_sigma);cached(p)
                        fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                            lambda z:np.array(list(slacks(p,z,d['original_entries'],bias_sigma).values()))-.01,
                            x,p.lower,p.upper,iterations=40)
                        x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][d['all_labels']],-15,15)
                        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-ref)))));ref=phase
                    record=summary(p,x,d['original_entries']);c=p.calculate(x)
                    record.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
                        joint_phase_reference=p.joint_reference,coefficient=c['coefficient'],noise_precision=c['noise_precision'],
                        relative_noise_precision=c['relative_noise_precision'],relative_gates=relative_gates(p,x,bias_sigma),
                        normalization_constant=c['normalization_constant'],minimum_gate_slack=min(slacks(p,x,d['original_entries'],bias_sigma).values()))
                    pair[arm]=record
                accepted=bool(valid(pair) and all(r['final_phase_change_s']<=.01 and all(g['compatible'] for g in r['relative_gates']) for r in pair.values()))
                result.update(arms=pair,accepted=accepted,policy_arms=pair if accepted else d['signed']['policy_arms'],
                    feasible_refinement_attempted=True,reason='bounded_original_gate_constraints')
    except Exception as exc:
        import traceback
        traceback.print_exc();result.update(feasible_refinement_attempted=True,refinement_error=repr(exc),
            accepted=False,policy_arms=saved.get('original_incumbent'))
    finally:signal.alarm(0)
    result['feasible_refinement_seconds']=time.monotonic()-began;write(path,result)
    print(case,variant,'feasible',result['accepted'],result.get('reason'),result.get('refinement_error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True)
    for name,source,cases in [('development',SOURCE,CASES),('confirmation20',SOURCE/'confirmation20',read(SOURCE/'confirmation20/protocol.json')['cases'])]:
        output=OUT/name;output.mkdir(exist_ok=True)
        protocol=dict(cases=cases,development_cases=CASES,variants=VARIANTS,default='joint_bias424',
            source_execution_sha256=sha(source/'execution.json'),source_preflight_sha256=sha(source/'control_audit.json') if name=='development' else sha(source/'preflight_execution.json'),
            gate_constraints_identical_original_thresholds=True,numerical_slack_interior=.01,near_gate_cutoff=-.25,
            steps_per_round=40,phase_rounds=5,workers=8,paired_cap_s=300,
            hypotheses_masks_priors_and_measurements_unchanged=True,original_incumbent_fallback_for_failure=True,
            no_GPS_inference_selection_or_future_TLE=True,starts_are_frozen_cold_regional_RF_endpoints=True,
            previously_inspected_comparison_cohort=True,same_site_not_new_location=True,
            source_sha256=sha(Path(__file__)))
        path=output/'protocol.json'
        if path.exists() and read(path)!=protocol:raise ValueError('feasible joint protocol changed')
        if not path.exists():write(path,protocol)
        preflight=read(source/'preflight_execution.json') if name=='confirmation20' else dict(rows=[],all_terminal=True)
        write(output/'preflight_execution.json',preflight)
        with ProcessPoolExecutor(max_workers=8) as pool:
            rows=[f.result() for f in as_completed([pool.submit(one,c,*v,source,output) for c in cases for v in VARIANTS])]
        write(output/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
