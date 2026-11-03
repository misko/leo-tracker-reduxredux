"""Fresh objective replay and all-candidate temporal check on final track rows."""
import importlib.metadata
import json
import platform
import numpy as np
from search import ROOT,observations
from timing_trials import restore
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular


def main():
    a,ctx,bank,model,fit,audit=restore();trial=json.loads((ROOT/'timing-trials.json').read_text())
    endpoint=np.load(ROOT/'trial-endpoint.npz');v=endpoint['vector'];n=endpoint['nuisance']
    ev,details=model.evaluate_details(v,n);saved=trial['trials'][-1]
    assert abs(ev[0]-saved['objective'])<1e-8 and abs(ev[3].nll-saved['NLL'])<1e-8
    original_v=np.array(fit['vector']);original_n=np.array(fit['nuisance'])
    np.testing.assert_array_equal(v[:7],original_v[:7])
    np.testing.assert_array_equal(n[:model.base_nuisance_count],original_n[:model.base_nuisance_count])
    old_tau=original_v[7]+model.basis@original_v[8:];new_tau=v[7]+model.basis@v[8:]
    nums=list(model.bank.numbers);edited={p['satellite'] for p in trial['profiles']}
    np.testing.assert_allclose([x for num,x in zip(nums,old_tau) if num not in edited],
        [x for num,x in zip(nums,new_tau) if num not in edited],atol=1e-12,rtol=0)
    # Independently select identity and timing from each training half, without
    # relying on the target-informed candidate labels in timing_trials.py.
    checks=[]
    for group in trial['profiles']:
        rows=np.array(group['rows']);obs=observations(a,ctx,rows);y=a['measured'][rows]-a['correction'][rows]
        masks={'early_to_late':obs.times_s<=np.median(obs.times_s),'late_to_early':obs.times_s>np.median(obs.times_s)}
        arms={'fitted-c':y,'zero-c-fixed':y+original_v[6]*(a['rf'][rows]-ctx['rf_center_hz'])/1e9}
        state={(arm,split):dict(score=np.full(len(bank.numbers),np.inf),timing=np.zeros(len(bank.numbers)),
            train=np.zeros(len(bank.numbers)),test=np.zeros(len(bank.numbers))) for arm in arms for split in masks}
        for shift in np.linspace(-5,5,201):
            pred,vis,_,_=predict_orbits(bank,obs,model.prior,original_v[:2],np.full(len(bank.numbers),shift),derivatives=False)
            for arm,yy in arms.items():
                residual=circular(yy[:,None]-pred)
                for split,mask in masks.items():
                    tr=np.mean(residual[mask]**2,axis=0);te=np.mean(residual[~mask]**2,axis=0)
                    score=mask.sum()*tr/125**2+(shift/2)**2;score[~vis[mask].all(axis=0)]=np.inf
                    s=state[arm,split];take=score<s['score'];s['score'][take]=score[take];s['timing'][take]=shift
                    s['train'][take]=tr[take];s['test'][take]=te[take]
        for (arm,split),s in state.items():
            k=int(np.argmin(s['score']));checks.append(dict(group=group['group'],arm=arm,split=split,
                satellite=int(bank.numbers[k]),timing_s=float(s['timing'][k]),
                training_rms_hz=float(np.sqrt(s['train'][k])),test_rms_hz=float(np.sqrt(s['test'][k]))))
            assert int(bank.numbers[k])==group['satellite']
    result=dict(saved_objective_audit=audit,final_objective_replay_error=abs(ev[0]-saved['objective']),
        position_receiver_calibration_and_non_target_timings_preserved=True,
        final_track_all_regional_training_only_identity_checks=checks,component_tests_passed=6,
        python=platform.python_version(),versions={name:importlib.metadata.version(name) for name in ['numpy','scipy','sgp4','matplotlib']},
        qualification='Conditional temporal checks at the saved full-scan position and calibration; '
        'orbit-blind track membership uses the complete interval. The diagnostic final endpoint '
        'was fitted using all scan observations, not held out. No identity truth or localization improvement claim.')
    (ROOT/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
