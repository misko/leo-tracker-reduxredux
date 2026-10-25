"""Bind all three matched-control batches before geographic reporting."""
from pathlib import Path
import numpy as np
from matched_controls import HERE,cohort,digest,load_protocol,read,write


def main():
    root=HERE.parent
    protocols=[root/'noise/position_protocol.json',root/'receiver/position_protocol_rf.json',root/'receiver/position_protocol_hz.json']
    models=[];bindings={};baselines={}
    for path in protocols:
        protocol,_=load_protocol(path)
        folder=HERE/'models'/protocol['model_id'];execution=read(folder/'execution.json')
        audit_path=folder/'independent_replay_audit.json';audit=read(audit_path)
        assert execution['all_terminal'] and execution['cases']==24 and execution['failed_trials']==0
        assert audit['passed'] and audit['cases']==24 and audit['replayed_arms']==48
        results=[]
        for case in cohort():
            p=folder/(case+'.json');r=read(p)
            assert r['status']=='complete' and set(r['arms'])=={'c0','fitted_c'}
            assert r['protocol_sha256']==digest(path) and r['GPS_used'] is False
            assert r['adopted']==r['paired_valid'] and r['policy_source']==('trial' if r['paired_valid'] else 'baseline')
            assert digest(r['baseline_path'])==r['baseline_sha256']
            if case in bindings:assert bindings[case]==r['input_binding_sha256']
            else:bindings[case]=r['input_binding_sha256']
            if case in baselines:assert baselines[case]['sha256']==r['baseline_sha256']
            else:baselines[case]=dict(path=r['baseline_path'],sha256=r['baseline_sha256'])
            for arm,s in r['arms'].items():
                assert s['active_points']==r['baseline'][arm]['active_points']
                assert np.isfinite(s['negative_twice_elbo']) and np.isfinite(s['RMS_hz'])
            results.append(dict(case=case,path=str(p),sha256=digest(p),paired_valid=r['paired_valid'],policy_source=r['policy_source']))
        models.append(dict(model_id=protocol['model_id'],protocol_path=str(path),protocol_sha256=digest(path),
            execution_sha256=digest(folder/'execution.json'),replay_audit_sha256=digest(audit_path),
            paired_cases=24,arm_results=48,trial_policy_cases=execution['trial_policy_cases'],
            baseline_policy_cases=execution['baseline_policy_cases'],results=results))
    write(HERE/'batch_seal.json',dict(passed=True,models=models,total_paired_cases=72,total_arm_results=144,
        all_original_baselines_unchanged=baselines,same_baseline_measurement_bindings_across_models=bindings,
        no_GPS_accessed_by_fitting_or_seal=True,no_between_variant_GPS_selection=True,
        orbital_alternative_qualification_failed_no_position_fit=True,
        source_sha256={p.name:digest(p) for p in [HERE/'matched_controls.py',HERE/'run_cohort.py',HERE/'audit_endpoints.py',Path(__file__)]}))
    print('sealed 72 paired cases / 144 arms; all replay audits pass',flush=True)


if __name__=='__main__':main()
