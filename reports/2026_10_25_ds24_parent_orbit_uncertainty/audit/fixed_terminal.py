"""Independent saved fixed-state gradient, covariance and ownership audit."""
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
from scipy.linalg import solve_triangular

ROOT=Path(__file__).resolve().parents[1]
SCI=ROOT/'scientific'


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def information(j,u,w,prior):
    full=np.vstack((np.column_stack((j,u))*np.sqrt(w[:,None]),
                    np.column_stack((np.zeros((len(prior),2)),np.diag(np.sqrt(prior))))))
    _,r=np.linalg.qr(full,mode='reduced')
    inv=solve_triangular(r,np.eye(len(r)),lower=False)
    return np.linalg.inv((inv@inv.T)[:2,:2])


def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('60s saved fixed audit cap')))
    signal.setitimer(signal.ITIMER_REAL,60.)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    protocol=read(SCI/'protocol.json');summary=read(SCI/'fixed_summary.json');seal=read(SCI/'fixed_seal.json')
    check('exact preflight protocol',sha(SCI/'protocol.json')==read(ROOT/'audit/preflight.json')['protocol_sha256'])
    for path,h in protocol['source_input_hashes'].items():check('source/input '+path,sha(path)==h)
    for path,h in seal['files'].items():check('fixed seal '+path,sha(path)==h)
    check('four terminal cases',summary['all_selected_terminal'] and [r['case'] for r in summary['cases']]==protocol['ordered_cases'])
    check('600s summed worker budget',summary['cumulative_charged_seconds']<=600.)
    max_info_error=0.;max_density_error=0.;contexts=0;triggers=[];rows=[]
    for case in summary['cases']:
        name=case['case'];reference=read(SCI/'fixed'/f'{name}_reference.json')
        check(name+' complete under case cap',case['status']=='complete' and case['scientific_seconds']<=120.)
        membership=reference['likelihood_membership'];ids=membership['curved_observation_ids']+membership['predictive_observation_ids']
        check(name+' exact native likelihood ownership',len(ids)==len(set(ids))==membership['union_unique'])
        parent=read(protocol['cases'][name]['baseline_path'])
        node=parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
        entries=parent['selected']['entries'] if parent['accepted'] else parent['baseline_entries']
        tracks={t['key']:t for t in read(Path(protocol['cases'][name]['baseline_path']).parents[2]/name/'tracks.json')}
        family={oid:r['candidate_index'] for r in node['seed']['rows'] for oid in tracks[r['component']]['observation_ids']}
        family.update({oid:e['candidate_index'] for e in entries for oid in e['observation_ids']})
        ownership=read(protocol['cases'][name]['original_ownership_path'])
        arms=[]
        for arm,row in case['arms'].items():
            contexts+=1;prefix=name+arm
            check(prefix+' actual-context controls all pass',row['controls']['all_passed'] and row['numerically_qualified'])
            check(prefix+' original ledger exact',reference['coverage'][arm]['accepted_observation_ids']==ownership['coverage'][arm]['accepted_observation_ids'])
            check(prefix+' old columns and zero gates/coverage exact',all(row['controls'][k] for k in ['old_columns_exact','zero_extra_coverage_exact','zero_extra_gates_exact','calculate_gate_extension_invariant']))
            check(prefix+' predictive no feedback',row['controls']['predictive_redaction']['coefficient_error']==0 and row['controls']['predictive_redaction']['Gamma_error']==0)
            for method in ('baseline','candidate'):
                probe=row[method]
                calculated=[]
                for step in probe['steps']:
                    h=step['step_km'];g=np.array([(b-a)/(2*h) for a,b in step['axis_minus_plus_objectives']])
                    check(prefix+method+' saved central gradient',np.array_equal(g,step['gradient']))
                    calculated.append(g)
                discrepancy=float(np.linalg.norm(calculated[0]-calculated[1]))
                check(prefix+method+' derivative qualification',discrepancy<=max(1e-3,1e-3*np.linalg.norm(calculated[0])))
                check(prefix+method+' decomposition',abs(probe['center']['decomposition_error'])<1e-6)
            delta=np.array(row['candidate']['gradient'])-row['baseline']['gradient']
            check(prefix+' actual model-change gradient',np.array_equal(delta,row['model_change_gradient']))
            arrays=dict(np.load(row['arrays']['path']))
            check(prefix+' appended shared columns exact',np.array_equal(arrays['augmented_u'],np.column_stack((arrays['old_u'],arrays['extra_columns']))) and np.array_equal(arrays['augmented_prior'],np.r_[arrays['old_prior'],np.ones(arrays['extra_columns'].shape[1])]))
            extra=row['new_prior_only_families'];check(prefix+' active-only missing-mode set',set(extra)==set(row['active_families'])-set(row['original_calibration_supported']))
            check(prefix+' one full3-mode block per family',arrays['extra_columns'].shape==(len(ids),3*len(extra)))
            for k,j in enumerate(extra):
                use=np.array([family[oid]==j for oid in ids])
                check(prefix+str(j)+' no loading on other families',np.count_nonzero(arrays['extra_columns'][~use,3*k:3*k+3])==0)
                check(prefix+str(j)+' active physical loading retained',np.linalg.norm(arrays['extra_columns'][use,3*k:3*k+3])>0)
            old=information(arrays['old_j'],arrays['old_u'],arrays['old_weights'],arrays['old_prior'])
            new=information(arrays['old_j'],arrays['augmented_u'],arrays['old_weights'],arrays['augmented_prior'])
            for actual,saved in ((old,arrays['old_information']),(new,arrays['augmented_information'])):
                error=float(np.linalg.norm(actual-saved)/np.linalg.norm(actual));max_info_error=max(max_info_error,error)
                check(prefix+' independent full joint QR',error<1e-8)
            check(prefix+' information loss PSD',np.linalg.eigvalsh((old-new+old.T-new.T)/2).min()>=-1e-8*max(1,np.linalg.norm(old)))
            weak=arrays['original_weak_axis'];oldvar=float(weak@np.linalg.solve(old,weak));newvar=float(weak@np.linalg.solve(new,weak))
            fraction=newvar/oldvar-1
            check(prefix+' fixed original weak variance',abs(fraction-row['weak_variance_fractional_change'])<1e-8)
            proxy=-.5*np.linalg.solve(old,delta)
            check(prefix+' movement factor and baseline information',np.linalg.norm(proxy-row['movement_proxy_km'])<1e-8)
            take=np.array(row['dense_oracle']['rows']);u=arrays['augmented_u'][take];w=arrays['old_weights'][take];p=arrays['augmented_prior']
            covariance=np.diag(1/w)+(u/p)@u.T;raw=np.sin(np.arange(len(take)))*20
            density=float(raw@np.linalg.solve(covariance,raw)+np.linalg.slogdet(covariance)[1]+len(raw)*np.log(2*np.pi))
            error=abs(density-row['dense_oracle']['nuisance_normalized_objective']);max_density_error=max(max_density_error,error)
            check(prefix+' actual sampled dense density oracle',error<1e-6)
            arms.append(dict(arm=arm,movement_proxy_norm_km=float(np.linalg.norm(proxy)),weak_variance_fractional_change=fraction))
        movement=all(a['movement_proxy_norm_km']>=.05 for a in arms)
        variance=all(a['weak_variance_fractional_change']>=.05 for a in arms)
        if movement or variance:triggers.append(dict(case=name,both_arms_movement=movement,both_arms_variance=variance))
        rows.append(dict(case=name,arms=arms))
    check('independent frozen triage',triggers==summary['triage']['triggers'] and bool(triggers)==summary['triage']['proceed_all_four_cases'])
    signal.setitimer(signal.ITIMER_REAL,0)
    output=dict(all_passed=True,checks=checks,contexts=contexts,rows=rows,triggers=triggers,
        maximum_information_relative_error=max_info_error,maximum_dense_density_error=max_density_error,
        seconds=time.monotonic()-began,source_sha256=sha(__file__),protocol_sha256=sha(SCI/'protocol.json'),fixed_seal_sha256=sha(SCI/'fixed_seal.json'),
        recommendation='fixed controls and frozen RF triage pass; coordinator may authorize the predeclared16-fit comparison, without operational adoption',
        propagation_calls=0,fits=0,GPS_or_position_errors_read=False)
    (ROOT/'audit/fixed_terminal.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('checks','rows')}))


if __name__=='__main__':main()
