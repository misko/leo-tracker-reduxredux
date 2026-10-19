"""Report matched Gaussian and robust satellite/fragment carrier hypotheses."""

import csv
import shutil
import tarfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_shared_carrier_constants import OUT, MODES
from probe_ds23_robust_carrier_constants import OUT as ROBUST
from report_algo01_ds23_sample import position_error, summarize
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, read, write, sha

ALL_MODES = [*MODES, 'robust100', 'robust30']


def csv_file(name, rows):
    with (OUT/name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def save(fig, name):
    fig.savefig(OUT/name, dpi=165)
    plt.close(fig)


def completed(folder, source):
    protocol, execution = read(folder/'protocol.json'), read(folder/'execution.json')
    cases = sorted(protocol['cases'])
    assert len(cases) == len(set(cases)) == len(execution) == 20
    assert {r['case'] for r in execution} == set(cases)
    assert all(r['code'] == 0 and r['result_sha256'] == sha(folder/(r['case']+'.json')) for r in execution)
    assert protocol['source_sha256'] == sha(ROOT/'tools'/source)
    assert protocol['sample_sha256'] == sha(SOURCE/'sample.json')
    assert cases == sorted(r['dataset_label'] for r in read(SOURCE/'sample.json')['selected'])
    return cases, {c:read(folder/(c+'.json')) for c in cases}


def run():
    cases, gaussian = completed(OUT/'incumbent/baseline', 'probe_ds23_shared_carrier_constants.py')
    robust_cases, robust = completed(ROBUST/'incumbent/baseline', 'probe_ds23_robust_carrier_constants.py')
    assert cases == robust_cases
    assert read(ROBUST/'incumbent/baseline/protocol.json')['prior_source_sha256'] == sha(ROOT/'tools/ds23_robust_carrier_prior.py')
    rows, raw_rows, choice_rows, dense_rows = [], [], [], []
    causal_receipts=[]
    for case in cases:
        g, d = gaussian[case], robust[case]
        assert d['source_sha256'] == sha(ROOT/'tools/probe_ds23_robust_carrier_constants.py')
        assert g['source_sha256'] == sha(ROOT/'tools/probe_ds23_shared_carrier_constants.py')
        assert d['gaussian_reference_sha256'] == sha(OUT/'incumbent/baseline'/(case+'.json'))
        assert d['mask'] == g['mask'] and g['no_GPS_used'] is True and d['no_GPS_used'] is True
        assert g['learned_prior_sha256'] == sha(ROOT/'reports/2026_10_18_ds23_history_calibrated_phase'/(case+'.json'))
        receipt_path=SOURCE/'causal_prior'/case/'receipt.json';receipt=read(receipt_path)
        assert not receipt['reference_position_used'] and receipt['search_box_width_km']==25
        assert max(receipt['latest_max_epoch_utc_ns'],receipt['latest_max_collection_utc_ns'])<receipt['cutoff_utc_ns']
        causal_receipts.append(dict(case=case,receipt_sha256=sha(receipt_path),cutoff_utc_ns=receipt['cutoff_utc_ns'],
            latest_max_epoch_utc_ns=receipt['latest_max_epoch_utc_ns'],latest_max_collection_utc_ns=receipt['latest_max_collection_utc_ns'],
            inherited_bank_sha256=receipt['bank_sha256'],search_center=receipt['search_center'],reference_position_used=False))
        for m in MODES:
            assert d['results'][m] == g['results'][m]
        valid = [m for m,r in d['results'].items() if r['paired_valid']]
        assert d['selected'] == min(valid, key=lambda m:d['results'][m]['arms']['c0']['negative_twice_elbo'])
        choice_rows.append(dict(case=case, Gaussian_choice=g['selected'], extended_choice=d['selected'],
            calibration_points=sum(d['mask'])))
        for arm in ('c0', 'fitted_c'):
            base = d['results']['independent']['arms'][arm]
            for m in ALL_MODES:
                r = d['results'][m]
                fit = r['arms'][arm]
                assert fit['active_points'] == base['active_points'] == sum(d['mask'])
                policy = fit if r['paired_valid'] else base
                raw_rows.append(dict(case=case, mode=m, arm=arm, paired_valid=r['paired_valid'],
                    raw_error_km=position_error(fit['endpoint_latlon']), RF_loss=fit['negative_twice_elbo'],
                    RMS_hz=fit['RMS_hz'], policy_error_km=position_error(policy['endpoint_latlon'])))
                rows.append(dict(case=case, policy=m, arm=arm, error_km=position_error(policy['endpoint_latlon']),
                    RF_loss=policy['negative_twice_elbo'], RMS_hz=policy['RMS_hz'], points=policy['active_points']))
            for name, selected in [('RF Gaussian',g['selected_arms']), ('RF extended',d['selected_arms'])]:
                fit = selected[arm]
                rows.append(dict(case=case, policy=name, arm=arm, error_km=position_error(fit['endpoint_latlon']),
                    RF_loss=fit['negative_twice_elbo'], RMS_hz=fit['RMS_hz'], points=fit['active_points']))
    policies = ALL_MODES+['RF Gaussian','RF extended']
    summary = {m:{a:summarize([r['error_km'] for r in rows if r['policy']==m and r['arm']==a]) for a in ('c0','fitted_c')} for m in policies}
    failures = {m:[c for c in cases if not robust[c]['results'][m]['paired_valid']] for m in ALL_MODES}
    for receiver in ('baseline','fast_rx1'):
        g = read(OUT/'dense'/receiver/'DS23-0202.json')
        d = read(ROBUST/'dense'/receiver/'DS23-0202.json')
        assert d['gaussian_reference_sha256'] == sha(OUT/'dense'/receiver/'DS23-0202.json')
        for m in ALL_MODES:
            r = d['results'][m]
            for arm,fit in r['arms'].items():
                dense_rows.append(dict(receiver=receiver, mode=m, arm=arm, paired_valid=r['paired_valid'],
                    error_km=position_error(fit['endpoint_latlon']), RF_loss=fit['negative_twice_elbo'],
                    RMS_hz=fit['RMS_hz'], points=fit['active_points']))
    catalogue = read(OUT/'catalogue/DS23-0202.json')
    plan = read(OUT/'catalogue/DS23-0202_plan.json')
    assert catalogue['plan_sha256'] == sha(OUT/'catalogue/DS23-0202_plan.json')
    assert plan['source_sha256'] == catalogue['source_sha256'] == sha(ROOT/'tools/probe_ds23_shared_carrier_catalogue.py')
    candidate_rows=[]
    winner = catalogue['chosen']['arms']['c0']['negative_twice_elbo']
    for trial in catalogue['trials']:
        for arm, fit in trial['arms'].items():
            candidate_rows.append(dict(norad=trial['proposal']['norad'], arm=arm, paired_valid=trial['paired_valid'],
                error_km=position_error(fit['endpoint_latlon']), RF_loss=fit['negative_twice_elbo'],
                RF_loss_above_c0_winner=fit['negative_twice_elbo']-winner))
    csv_file('position_by_scan.csv', rows)
    write(OUT/'input_receipt_audit.json',dict(cases=causal_receipts,original_causal_cutoffs_rechecked=True,bank_not_rehashed_by_this_report=True))
    csv_file('raw_trials.csv', raw_rows)
    csv_file('selected_hypotheses.csv', choice_rows)
    csv_file('dense202_trials.csv', dense_rows)
    csv_file('dense202_identities.csv', candidate_rows)
    write(OUT/'summary.json', dict(cases=cases, policies=summary, paired_failures=failures,
        choices={m:sum(d['selected']==m for d in robust.values()) for m in ALL_MODES},
        Gaussian_choices={m:sum(d['selected']==m for d in gaussian.values()) for m in MODES},
        dense202=dense_rows, dense202_catalogue=candidate_rows,
        fresh_catalogue_size=plan['catalogue_size'], fresh_finalists=len(catalogue['trials']),
        RF_selected_norad=catalogue['chosen']['proposal']['norad'], original20_development_only=True,
        all_DS23_and_new_location_target_verified=False, target_met=False,
        report_source_sha256=sha(Path(__file__))))

    fig,axes=plt.subplots(2,1,figsize=(15,8),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for policy,color,marker in [('independent','0.5','o'),('RF Gaussian','tab:orange','x'),('RF extended','tab:blue','.')]:
            rr=[next(r for r in rows if r['case']==c and r['arm']==arm and r['policy']==policy) for c in cases]
            ax.plot(range(20),[r['error_km'] for r in rr],lw=.8,color=color,marker=marker,label=policy)
        ax.axhline(.5,color='crimson',ls='--',lw=.7)
        ax.set(ylabel='Position error (km)',title=arm)
        ax.legend(fontsize=8)
        ax.grid(alpha=.2)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=90)
    fig.suptitle('Same twenty development scans · RF-only prior selection · no calibration-point removal')
    save(fig,'cohort_position.png')

    fig,axes=plt.subplots(1,2,figsize=(14,5),constrained_layout=True)
    labels=['Independent','Old ρ=.9','Gaussian δ100','Gaussian δ30','Student δ100','Student δ30']
    for k,arm in enumerate(('c0','fitted_c')):
        axes[0].bar(np.arange(6)+(k-.5)*.32,[summary[m][arm]['mean_km'] for m in ALL_MODES],width=.3,label=arm)
    axes[0].set_xticks(range(6),labels,rotation=25,ha='right',fontsize=8)
    axes[0].set(ylabel='Mean policy position error (km)',title='Paired gate failure falls back to independent model')
    axes[0].legend(fontsize=8)
    axes[1].bar(range(6),[len(failures[m]) for m in ALL_MODES],color='tab:orange')
    axes[1].set_xticks(range(6),labels,rotation=25,ha='right',fontsize=8)
    axes[1].set(ylabel='Paired gate failures / 20',title='Every failed raw trial remains in the evidence archive')
    for ax in axes:ax.grid(axis='y',alpha=.2)
    save(fig,'cohort_hypotheses.png')

    fig,axes=plt.subplots(1,3,figsize=(16,5),constrained_layout=True)
    colors=dict(zip(ALL_MODES,['0.5','tab:purple','tab:orange','tab:green','tab:blue','tab:red'],strict=True))
    for ax,receiver in zip(axes[:2],('baseline','fast_rx1'),strict=True):
        for r in dense_rows:
            if r['receiver']==receiver and r['arm']=='c0':
                ax.scatter(r['error_km'],r['RF_loss'],color=colors[r['mode']],marker='o' if r['paired_valid'] else 'x',label=r['mode'])
        ax.set(xlabel='Position error c=0 (km)',ylabel='Normalized RF loss',title='Slow receiver' if receiver=='baseline' else 'Experimental fast RX1')
        ax.legend(fontsize=7)
        ax.grid(alpha=.2)
    for r in candidate_rows:
        if r['arm']!='c0':continue
        axes[2].scatter(r['error_km'],r['RF_loss_above_c0_winner'],marker='o' if r['paired_valid'] else 'x')
        axes[2].annotate(str(r['norad']),(r['error_km'],r['RF_loss_above_c0_winner']),xytext=(3,3),textcoords='offset points',fontsize=7)
    axes[2].set(xlabel='Position error c=0 (km)',ylabel='RF loss above winner',title='Fresh 1,569-candidate screen; seven full finalists')
    axes[2].grid(alpha=.2)
    save(fig,'dense202_RF_and_accuracy.png')

    fig,axes=plt.subplots(1,2,figsize=(14,5),constrained_layout=True)
    d=read(ROBUST/'dense/fast_rx1/DS23-0202.json')
    for mode in ('robust100','robust30'):
        tracks=d['results'][mode]['arms']['c0']['tracks']
        axes[0].scatter([abs(t['fragment_contrast_hz']) for t in tracks],[t['contrast_precision'] for t in tracks],s=17,alpha=.7,label=mode)
    axes[0].set(xlabel='Absolute posterior fragment deviation (Hz)',ylabel='Contrast precision multiplier',yscale='log',title='Low precision permits a larger deviation; not identity probability')
    axes[0].legend(fontsize=8)
    for receiver,style in [('baseline','-'),('fast_rx1','--')]:
        data=read(ROBUST/'dense'/receiver/'DS23-0202.json')
        for mode in ('shared30','robust30'):
            fit=data['results'][mode]['arms']['c0']
            target=next(t for t in fit['gates']['tracks'] if '-RX1-CH5-T006-' in t['component'])
            axes[1].plot([0,1],[target['profile_noise']['maximum_step_z'],target['conditional_noise']['maximum_step_z']],style,marker='o',label=receiver+' / '+mode)
    axes[1].axhline(4,color='crimson',lw=.8)
    axes[1].set_xticks([0,1],['Profile','Conditional'])
    axes[1].set(ylabel='Maximum step statistic',title='RX1 CH5 T006, satellite 62503 · unchanged threshold 4')
    axes[1].legend(fontsize=7)
    for ax in axes:ax.grid(alpha=.2)
    save(fig,'contrasts_and_gate.png')
    package(cases)
    write(OUT/'validation.json',dict(all20_Gaussian_and_robust_processes_completed=True,
        execution_result_hashes_and_sources_match=True, all_original_point_counts_preserved=True,
        inherited_Gaussian_trials_match_exactly=True, selection_recomputed_without_GPS=True,
        owned_tests_observed_passed=10, no_RF_IQ_recording_or_production_change=True,
        target_reached_on_full_DS23=False))
    print('Shared carrier policies',summary,flush=True)
    print('Extended choices',{m:sum(d['selected']==m for d in robust.values()) for m in ALL_MODES},flush=True)


def package(cases):
    paths=[]
    for directory in (OUT,ROBUST):
        paths += [directory/'incumbent/baseline'/(case+'.json') for case in cases]
        paths += [directory/'incumbent/baseline'/name for name in ('protocol.json','execution.json')]
        paths += [directory/'dense'/r/'DS23-0202.json' for r in ('baseline','fast_rx1')]
    paths += [OUT/'catalogue'/name for name in ('DS23-0202_plan.json','DS23-0202.json')]
    paths += [ROBUST/'pilot_v1/dense'/r/'DS23-0202.json' for r in ('baseline','fast_rx1')]
    paths += [ROBUST/'prior_collapse_parity.json']
    with tarfile.open(OUT/'evidence.tar.xz','w:xz',preset=6) as archive:
        for path in paths:archive.add(path,arcname=str(path.relative_to(ROOT)))
    write(OUT/'evidence_inventory.json',{str(p.relative_to(ROOT)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in paths})
    sources=['tools/'+n+'.py' for n in ('probe_ds23_shared_carrier_constants','run_ds23_shared_carrier_cohort',
        'ds23_correlated_family_screen','probe_ds23_shared_carrier_catalogue','probe_ds23_robust_carrier_constants',
        'ds23_robust_carrier_prior','run_ds23_robust_carrier_cohort','report_ds23_carrier_study','probe_ds23_cross_rf_constants')]
    sources += ['tests/analysis/'+n+'.py' for n in ('test_ds23_shared_carrier_constants','test_ds23_correlated_family_screen','test_ds23_robust_carrier_constants')]
    inventory={}
    for name in sources:
        destination=OUT/'source_snapshot'/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,destination);inventory[str(destination.relative_to(OUT))]=sha(destination)
    source=ROBUST/'source_v1/tools/probe_ds23_robust_carrier_constants.py'
    destination=OUT/'source_v1/tools'/source.name;destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination);inventory[str(destination.relative_to(OUT))]=sha(destination)
    write(OUT/'source_inventory.json',inventory)


if __name__=='__main__':run()
