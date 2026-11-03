"""Hardware-prior sensitivity under an in-model receiver perturbation.

All changed CFOs live in a synthetic in-memory scan. They are never persisted
as GLRT observations or used as extra measurements of the supplied location.
"""

import argparse
import copy
import time
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_calibration_mean import mean_problem
from ds23_predictive_linear import attach_predictive_linear
from investigate_dsx01_localization_failures import fit
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import OUT as GAUSSIAN
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/'reports/2026_10_19_ds23_receiver_invariance'
SCENARIOS=[('null',0.,0.),('plus_uncompensated',1.,0.),('minus_uncompensated',-1.,0.),
           ('plus_compensated',1.,1.),('minus_compensated',-1.,-1.)]


def run_fit(scan,node,keep,powers,means,model,arm,entries,index,prior_kappa,position=None):
    reference=np.zeros(len(means));x=np.zeros(2) if position is None else np.asarray(position,float);history=[]
    for _ in range(5):
        p=mean_problem(scan,node,keep,arm,reference,powers,means,model,index,prior_kappa)
        attach_predictive_linear(p,entries,powers)
        if position is None:
            r=fit(p,x,iterations=48);x=np.array(r['parameters'])
        else:r=dict(parameters=x,fixed_position=True)
        c=p.calculate(x);next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=r,phase_change_s=float(max(abs(next_phase-reference)))))
        reference=next_phase
    cg=p.curved_calculate(x) if entries else c;linear=[]
    for e,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=scan.tracks[e['track_index']];raw=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(raw,np.zeros(len(raw)),*scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        passing=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
            and noise['noise_screen_pass'][0] and min(c['linear_elevation'][sl])>=0)
        linear.append(dict(component=e['component'],compatible=passing,points=e['points'],observation_ids=e['observation_ids']))
    gates=retained_metrics(p,x)
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),phase_reference=p.reference,history=history,
        negative_twice_elbo=c['negative_twice_elbo'],curved_objective=cg['negative_twice_elbo'],
        linear_predictive_objective=c.get('linear_predictive_objective',0.),gates=gates,linear_gates=linear,
        compatible=all(t['compatible'] for t in gates['tracks']+linear) and history[-1]['phase_change_s']<=.01,
        active_points=int(keep.sum()),additional_points=sum(e['points'] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))))


def perturb(scan,receiver,basis_index,kappa):
    result=copy.copy(scan);result.tracks=[]
    for i,t in enumerate(scan.tracks):
        delta=(kappa*200.*(t['rf_hz']/11.5e9)*scan.rx_basis[i][:,basis_index] if t['receiver']==receiver else np.zeros(len(t['values'])))
        result.tracks.append(dict(t,values=np.array(t['values'])+delta))
    return result


def run(case):
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/(case+'.json')).exists():raise FileExistsError('preserve scientific outputs')
    scan,node,keep,powers,means,model,_,_=context(case,'archived');g=read(GAUSSIAN/(case+'.json'))
    v=g['results']['all_linear'];entries=v['entries'] if v['paired_valid'] else []
    p=make_problem(scan,node,keep,'c0',np.zeros(len(means)),powers,means,model['multiplier'],model['nu'])
    counts={rx:sum(int(keep[sl].sum()) for i,sl in zip(p.members,p.slices,strict=True) if scan.tracks[i]['receiver']==rx) for rx in (1,2)}
    receiver=max(counts,key=counts.get);width=scan.rx_basis[0].shape[1];basis_index=width//2;index=(receiver-1)*width+basis_index
    column=p.smooth[keep,index]*200.;target=np.concatenate([np.full(int(keep[sl].sum()),scan.tracks[i]['receiver']==receiver) for i,sl in zip(p.members,p.slices,strict=True)])
    rms=float(np.sqrt(np.mean(column[target]**2)));results={}
    for name,data_shift,mean_shift in SCENARIOS:
        modified=perturb(scan,receiver,basis_index,data_shift)
        pair={arm:run_fit(modified,node,keep,powers,means,model,arm,entries,index,mean_shift) for arm in ('c0','fitted_c')}
        fixed={}
        if name.endswith('uncompensated'):
            fixed={arm:run_fit(modified,node,keep,powers,means,model,arm,entries,index,mean_shift,
                results['null']['arms'][arm]['endpoint_east_north_km']) for arm in ('c0','fitted_c')}
        results[name]=dict(arms=pair,fixed_original_coordinate=fixed,paired_valid=all(r['compatible'] for r in pair.values()))
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,name,'paired valid',results[name]['paired_valid'],flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,receiver=receiver,basis_index=basis_index,
        one_prior_SD_injected_RMS_hz=rms,one_prior_SD_peak_hz=float(max(abs(column))),original_arms=v['policy_arms'],
        synthetic_in_memory_CFO_changes_only=True,original_records_never_mutated=True,no_GPS_used=True,
        same_original_masks_aliases_labels_noise_and_c_pair_data=True,known_mean_translation_is_a_control_not_a_deployable_fix=True,
        gaussian_input_sha256=sha(GAUSSIAN/(case+'.json')),source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_calibration_mean.py'),seconds=time.monotonic()-started))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
