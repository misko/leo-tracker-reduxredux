"""Check stationary-prefix positions against all current-scan physical gates.

This is a fixed-position replay, not a history-aware RF optimizer. The same-site
assumption and lack of a movement/reset model still prevent default promotion.
"""

from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_predictive_linear import attach_predictive_linear
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import OUT as GAUSSIAN
from probe_ds23_robust_predictive_linear import OUT
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile


def at_fixed_position(scan,node,keep,powers,means,model,arm,entries,position):
    x=np.asarray(position,float);reference=np.zeros(len(means));history=[]
    for _ in range(5):
        p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
        attach_predictive_linear(p,entries,powers);c=p.calculate(x)
        next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(maximum_phase_reference_change_s=float(max(abs(next_phase-reference)))))
        reference=next_phase
    gates=retained_metrics(p,x);linear=[]
    for e,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=scan.tracks[e['track_index']];raw=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(raw,np.zeros(len(raw)),*scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        valid=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
            and noise['noise_screen_pass'][0] and min(c['linear_elevation'][sl])>=0)
        linear.append(dict(component=e['component'],compatible=valid,points=e['points'],observation_ids=e['observation_ids'],
            rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),noise_screen={k:v[0] for k,v in noise.items()}))
    valid=all(t['compatible'] for t in gates['tracks']+linear) and history[-1]['maximum_phase_reference_change_s']<=.01
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),gates=gates,linear_gates=linear,compatible=valid,
        active_points=int(keep.sum()),additional_predictive_points=sum(e['points'] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),state=p.state(x),history=history,
        negative_twice_elbo=c['negative_twice_elbo'],calibration_only_from_current_curved_data=True)


def run():
    path=OUT/'history_gate_replay.json'
    if path.exists():raise FileExistsError('preserve scientific replay')
    history=read(OUT/'stationary_history_diagnostic.json')['results']['gaussian']
    positions={arm:{r['case']:r['position_east_north_km'] for r in h['estimates']} for arm,h in history.items()}
    records=[]
    for case in sorted(positions['c0']):
        scan,node,keep,powers,means,model,_,_=context(case,'archived');g=read(GAUSSIAN/(case+'.json'))
        v=g['results']['all_linear'];entries=v['entries'] if v['paired_valid'] else []
        pair=v['policy_arms'];controls={}
        for name in ('individual_null','stationary_prefix'):
            arms={arm:at_fixed_position(scan,node,keep,powers,means,model,arm,entries,
                pair[arm]['endpoint_east_north_km'] if name=='individual_null' else positions[arm][case]) for arm in ('c0','fitted_c')}
            valid=all(a['compatible'] for a in arms.values())
            controls[name]=dict(arms=arms,paired_valid=valid,policy_arms=arms if valid else pair)
        records.append(dict(case=case,controls=controls,incumbent_arms=pair,
            current_gaussian_pair_qualified=v['paired_valid'],gaussian_input_sha256=sha(GAUSSIAN/(case+'.json'))))
        write(OUT/'history_gate_replay_partial.json',dict(records=records))
        print(case,'null/prefix',controls['individual_null']['paired_valid'],controls['stationary_prefix']['paired_valid'],flush=True)
    write(path,dict(records=records,no_GPS_used=True,no_new_position_optimization=True,
        fixed_position_five_phase_refreshes=True,current_policy_evidence_preserved_both_c_arms=True,
        stationary_assumption_still_unverified=True,no_movement_reset_model=True,
        history_input_sha256=sha(OUT/'stationary_history_diagnostic.json'),source_sha256=sha(Path(__file__))))


if __name__=='__main__':run()
