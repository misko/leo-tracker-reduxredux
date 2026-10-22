"""Audit family replacement inference and report matched adoption controls."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
import csv
import gc
import hashlib
import multiprocessing
import traceback
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from audit_ds23_family_cavity import nomination as audit_nomination,position as audit_position
from probe_ds23_family_cavity_nominations import OUT as DEFAULT,setup
from run_algo01_ds23_sample import ROOT,read,write,sha


def audit_dependencies():
    """Invalidate checkpoints after any local Python dependency changes."""
    paths=sorted([*(ROOT/'tools').glob('*.py'),*(ROOT/'src').rglob('*.py')])
    return hashlib.sha256(''.join(str(p.relative_to(ROOT))+sha(p) for p in paths).encode()).hexdigest()


def checkpoint_audit(case,stage,directory,execution_sha256,dependency_sha256):
    """Keep completed per-case checks when another case exposes an audit defect."""
    directory=Path(directory);source=directory/(case+'_nominations.json') if stage=='nominations' else directory/'position'/(case+'.json')
    checkpoint=directory/'position'/'audit_checkpoints'/stage/(case+'.json')
    signature=dict(source_sha256=sha(source),execution_sha256=execution_sha256,dependency_sha256=dependency_sha256)
    if checkpoint.exists():
        old=read(checkpoint)
        if old.get('signature')==signature and old.get('status')=='passed':return old
    try:
        result=audit_nomination(case,nominations_dir=directory) if stage=='nominations' else audit_position(case,position_dir=directory/'position')
        receipt=dict(case=case,stage=stage,status='passed',signature=signature,result=result)
    except Exception as exc:
        receipt=dict(case=case,stage=stage,status='failed',signature=signature,error=repr(exc),traceback=traceback.format_exc())
    checkpoint.parent.mkdir(parents=True,exist_ok=True)
    write(checkpoint,receipt)
    print(stage,case,receipt['status'],receipt.get('error',''),flush=True)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,default=DEFAULT)
    parser.add_argument('--workers',type=int,default=12)
    args=parser.parse_args();directory=args.directory;out=directory/'position'
    protocol=read(directory/'protocol.json');cases=protocol['cases'];execution_path=out/'execution.json';execution_sha256=sha(execution_path)
    execution=read(execution_path);assert execution['all_terminal']
    if (directory/'edge_repair_manifest.json').exists():
        repairs=read(directory/'edge_repair_manifest.json')
        assert repairs['nomination_complete']==repairs['position_complete']==len(cases)
    lookup={r['case']:r for r in execution['rows']};assert set(lookup)==set(cases)
    complete=[c for c in cases if lookup[c]['status']=='complete']
    del lookup,execution
    gc.collect()
    if not 1<=args.workers<=30:raise ValueError('between1and30audit workers required')
    dependency_sha256=audit_dependencies();attempts={}
    for stage in ['nominations','positions']:
        with ProcessPoolExecutor(max_workers=min(args.workers,len(complete)),mp_context=multiprocessing.get_context('spawn')) as pool:
            attempts[stage]=list(pool.map(partial(checkpoint_audit,stage=stage,directory=directory,
                execution_sha256=execution_sha256,dependency_sha256=dependency_sha256),complete))
        failures=[r for r in attempts[stage] if r['status']!='passed']
        write(out/'independent_audit_progress.json',dict(source_execution_sha256=execution_sha256,
            dependency_sha256=dependency_sha256,stages={k:dict(passed=sum(r['status']=='passed' for r in v),
            failed=sum(r['status']!='passed' for r in v)) for k,v in attempts.items()},failures=failures,
            geographic_evaluation_started=False))
        if failures:raise ValueError(f'{len(failures)} {stage} audits failed; see per-case checkpoints; no geographic evaluation performed')
    nominations=[r['result'] for r in attempts['nominations']];positions=[r['result'] for r in attempts['positions']]
    if sha(execution_path)!=execution_sha256:raise ValueError('execution snapshot changed during audit; no geographic evaluation allowed')
    if audit_dependencies()!=dependency_sha256:raise ValueError('audit dependency changed during audit; no geographic evaluation allowed')
    write(out/'independent_numerical_audit.json',dict(nominations=nominations,positions=positions,all_passed=True,
        source_execution_sha256=execution_sha256,
        full_causal_catalogue_and_held_observation_disjointness=True,
        expected_log_density_and_dense_or_SVD_predictive_reference=True,
        alternate_exact_orbits_and_finite_modes_and_original_gates=True,reference_position_used=False))
    # All inference and auditing above precedes reading evaluation coordinates.
    from report_algo02_ds23 import position_error
    execution=read(execution_path);lookup={r['case']:r for r in execution['rows']}
    rows=[];trials=[];statistics={};policies=['equal_assignment_priors','incumbent_sticky_prior']
    for case in cases:
        saved=lookup[case];incumbent=saved.get('baseline_arms') or setup(case)['signed']['policy_arms']
        options=[t for t in saved.get('trials',[]) if t['paired_valid']]
        best=min(options,key=lambda r:r['arms']['c0']['corrected_selection_loss']) if options else None
        delta=saved['baseline_corrected_loss']['c0']-best['arms']['c0']['corrected_selection_loss'] if best else None
        for policy in policies:
            penalty=0 if policy=='equal_assignment_priors' else saved.get('search_penalty',float('inf'))
            accepted=bool(best is not None and delta>penalty)
            for arm in ['c0','fitted_c']:
                original=incumbent[arm];record=best['arms'][arm] if accepted else original
                rows.append(dict(case=case,policy=policy,arm=arm,status=saved['status'],accepted=accepted,
                    original_error_km=position_error(original['endpoint_latlon']),policy_error_km=position_error(record['endpoint_latlon']),
                    frequency_RMS_hz=record['RMS_hz'],original_frequency_RMS_hz=original['RMS_hz'],
                    RF_selection_gain=delta,penalty=penalty,replacements=best['replacements'] if accepted else []))
        for trial in saved.get('trials',[]):
            for arm,r in trial['arms'].items():
                trials.append(dict(case=case,arm=arm,paired_valid=trial['paired_valid'],replacements=trial['replacements'],
                    raw_error_km_report_only=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],
                    corrected_loss=r['corrected_selection_loss'],RF_gain=saved['baseline_corrected_loss'][arm]-r['corrected_selection_loss'],
                    failed_curved=sum(not g['compatible'] for g in r['gates']['tracks']),
                    failed_predictive=sum(not g['compatible'] for g in r['linear_gates'])))
    for policy in policies:
        statistics[policy]={}
        for arm in ['c0','fitted_c']:
            selected=[r for r in rows if (r['policy'],r['arm'])==(policy,arm)]
            old=np.array([r['original_error_km'] for r in selected]);new=np.array([r['policy_error_km'] for r in selected]);delta=new-old
            rng=np.random.default_rng(2026102204);ix=rng.integers(0,len(new),size=(5000,len(new)))
            statistics[policy][arm]=dict(count=len(new),accepted=sum(r['accepted'] for r in selected),
                original_mean_km=float(old.mean()),original_median_km=float(np.median(old)),policy_mean_km=float(new.mean()),
                policy_median_km=float(np.median(new)),improved=int(np.sum(delta< -1e-6)),worsened=int(np.sum(delta>1e-6)),
                p90_km=float(np.percentile(new,90)),maximum_km=float(new.max()),at_most0p5km=int(np.sum(new<=.5)),
                paired_bootstrap_mean_change95_km=np.percentile(np.mean(delta[ix],axis=1),[2.5,97.5]),
                paired_bootstrap_median_change95_km=np.percentile(np.median(new[ix],axis=1)-np.median(old[ix],axis=1),[2.5,97.5]))
    write(out/'evaluation.json',dict(rows=rows,trials=trials,statistics=statistics,report_only_GPS=True,
        exact_incumbent_fallback_for_every_failed_job_and_gate=True,
        same_observations_candidate_fits_and_priors_for_both_adoption_rules=True,
        equal_assignment_model_prior_is_a_hypothesis_not_independently_verified_identity=True,
        same_site_and_older_methods_may_have_inspected_scans=True,no_new_location_validation=True,
        evaluated_cases=len(cases),evaluated_case_ids=cases,goal_achievement_must_be_checked_on_full_population=True))
    with (out/'positions.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained');x=np.arange(len(cases))
    for policy,color,marker in [('equal_assignment_priors','#168b91','o'),('incumbent_sticky_prior','#8765b4','s')]:
        selected=[next(r for r in rows if (r['case'],r['policy'],r['arm'])==(case,policy,'fitted_c')) for case in cases]
        error=np.array([r['policy_error_km'] for r in selected]);old=np.array([r['original_error_km'] for r in selected])
        axes[0].scatter(x,error,c=color,marker=marker,s=32,label=policy)
        axes[1].plot(np.sort(error),np.arange(1,len(error)+1)/len(error),c=color,label=policy)
    axes[0].scatter(x,old,c='black',marker='x',s=35,label='Original signed-prior incumbent')
    axes[1].plot(np.sort(old),np.arange(1,len(old)+1)/len(old),c='black',label='Original incumbent')
    axes[0].set_xticks(x,[c.split('-')[1] for c in cases],rotation=70,fontsize=8)
    axes[0].set(xlabel='DS23 scan',ylabel='Position error (km)');axes[1].set(xlabel='Position error (km)',ylabel='Empirical CDF')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Active-family replacement from covariance-aware family-excluded prediction\nAll original points restored; both calibration arms gated; all fallbacks counted')
    fig.savefig(out/'position_comparison.png',dpi=160);plt.close(fig)
    print(statistics,flush=True)


if __name__=='__main__':main()
