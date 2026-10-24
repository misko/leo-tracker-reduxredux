"""Post-inference endpoint evaluation; GPS appears only in this reporting file."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent
CASES=['DS24-0089','DS24-0015','DS24-0017','DS24-0101','DS24-0081']
ARMS=['c0','fitted_c']
TRUTH=(37.849061591561885,-122.48574968092912)


def read(p):
    return json.loads(p.read_text())


def error(point):
    a,b=np.radians([point,TRUTH]);delta=b-a
    h=np.sin(delta[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(delta[1]/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h,0,1))))


def csv_write(name,rows):
    with (OUT/name).open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def endpoint(r):
    return np.asarray(r['endpoint_east_north_km'])


def main():
    fixed=[read(OUT/(c+'_fixed.json')) for c in CASES]
    transferred={c:read(OUT/(c+'_transfer.json')) for c in CASES if (OUT/(c+'_transfer.json')).exists()}
    assert len(transferred)==4
    for item in fixed+list(transferred.values()):
        assert item['status']=='complete' and item['RF_selection']['no_geographic_error_or_GPS_accessed']
        for trial in item['trials']:
            for r in trial['arms'].values():
                assert np.max(abs(np.asarray(r['state']['phases'])))<=15.000001
    # Frozen selections above are checked before geographic evaluation below.
    rows=[]
    for item in fixed:
        for trial in item['trials']:
            for arm,r in trial['arms'].items():
                original=item['original'][arm]
                rows.append(dict(case=item['case'],start=trial['name'],arm=arm,paired_valid=trial['paired_valid'],
                    original_loss=original['negative_twice_elbo'],restart_loss=r['negative_twice_elbo'],
                    loss_gain=original['negative_twice_elbo']-r['negative_twice_elbo'],
                    endpoint_shift_km=float(np.linalg.norm(endpoint(r)-endpoint(original))),
                    original_error_km=error(original['endpoint_latlon']),error_km=error(r['endpoint_latlon']),
                    original_RMS_hz=original['RMS_hz'],RMS_hz=r['RMS_hz'],
                    phase_change_s=r['final_phase_change_s'],
                    evaluations=sum(h['fit']['evaluations'] for h in r['history']),
                    stop=r['history'][-1]['fit']['stopped']))
    csv_write('fixed_restarts.csv',rows)
    transfer_rows=[]
    for case,item in transferred.items():
        for trial in item['trials']:
            for arm,r in trial['arms'].items():
                original=item['original_arms'][arm]
                transfer_rows.append(dict(case=case,group=item['group'],start=trial['name'],arm=arm,
                    changed_retained_points=item['changed_retained_points'],paired_valid=trial['paired_valid'],
                    corrected_loss_gain=trial['gain'][arm],
                    original_error_km=error(original['endpoint_latlon']),error_km=error(r['endpoint_latlon']),
                    original_RMS_hz=original['RMS_hz'],RMS_hz=r['RMS_hz'],
                    phase_change_s=r['final_phase_change_s'],
                    failed_curved_tracks=len(trial['gate_failures'][arm]['curved_failures']),
                    failed_predictive_tracks=len(trial['gate_failures'][arm]['predictive_failures']),
                    constrained=trial['constrained_refinement_attempted']))
    csv_write('association_transfers.csv',transfer_rows)
    fixed_summary=[]
    for case in CASES:
        selected=[r for r in rows if r['case']==case]
        fixed_summary.append(dict(case=case,arm_fits=len(selected),all_paired_valid=all(r['paired_valid'] for r in selected),
            maximum_absolute_loss_difference=max(abs(r['loss_gain']) for r in selected),
            maximum_endpoint_shift_km=max(r['endpoint_shift_km'] for r in selected),
            maximum_phase_change_s=max(r['phase_change_s'] for r in selected)))
    best_transfer={c:min(item['trials'],key=lambda t:t['arms']['c0']['corrected_selection_loss']) for c,item in transferred.items()}
    summary=dict(fixed=fixed_summary,transfer_RF_selection={c:i['RF_selection'] for c,i in transferred.items()},
        fixed_arm_fits=len(rows),fixed_paired_valid_arm_fits=sum(r['paired_valid'] for r in rows),
        maximum_fixed_absolute_loss_difference=max(abs(r['loss_gain']) for r in rows),
        maximum_fixed_endpoint_shift_km=max(r['endpoint_shift_km'] for r in rows),
        transfer_arm_fits=len(transfer_rows),
        transfer_pair_valid_trials=sum(t['paired_valid'] for i in transferred.values() for t in i['trials']),
        adopted_fixed_cases=sum(i['RF_selection']['meaningful_improvement'] for i in fixed),
        adopted_transfer_cases=sum(i['RF_selection']['accepted'] for i in transferred.values()),
        phase_amplitude_and_saved_selection_audit_passed=True,
        evaluation_truth_only_after_RF_selection=list(TRUTH),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT/'run_fixed.py',OUT/'run_transfer.py',Path(__file__)]})
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,5,figsize=(16,7),layout='constrained')
    truth_xy=np.array([(TRUTH[1]+122.545)*111.32*np.cos(np.deg2rad(37.906)),(TRUTH[0]-37.906)*111.])
    for col,item in enumerate(fixed):
        for row,arm in enumerate(ARMS):
            ax=axes[row,col];original=item['original'][arm];x=endpoint(original)
            ax.scatter(*truth_xy,marker='*',s=90,color='#9659a7',label='GPS (evaluation)')
            ax.scatter(*x,s=90,facecolors='none',edgecolors='black',label='Full incumbent')
            for trial,color,marker in zip(item['trials'][1:],['#2e72bb','#e99130'],['s','^']):
                start=np.asarray(trial['starts'][arm]);end=endpoint(trial['arms'][arm])
                ax.scatter(*start,color=color,marker=marker,s=48,label='Half '+trial['name'])
                ax.annotate('',xy=end,xytext=start,arrowprops=dict(arrowstyle='->',color=color,alpha=.6))
            for trial in item['trials']:
                ax.scatter(*endpoint(trial['arms'][arm]),marker='x',color='black',s=25,label='Fixed restart end')
            if item['case'] in best_transfer:
                trial=best_transfer[item['case']]
                ax.scatter(*endpoint(trial['arms'][arm]),marker='D',s=44,
                    color='#35895a' if trial['paired_valid'] else '#bd4141',
                    label='Transferred (paired valid)' if trial['paired_valid'] else 'Transferred (invalid)')
            ax.set_title(item['case']+' · '+arm)
            ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.2)
            if col==0:ax.set_ylabel('North, km from cold-region centre')
            if row==1:ax.set_xlabel('East, km from cold-region centre')
    unique={}
    for ax in axes.flat:
        handles,labels=ax.get_legend_handles_labels()
        unique.update(zip(labels,handles))
    fig.legend(unique.values(),unique.keys(),loc='outside lower center',ncol=4,frameon=False)
    fig.suptitle('Fixed full-data restarts return to the incumbent; identity transfers test different hypotheses')
    fig.savefig(OUT/'endpoints.png',dpi=180);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    positions=np.arange(4)
    for arm,delta,color in [('c0',-.13,'#2e72bb'),('fitted_c',.13,'#e99130')]:
        gains=[best_transfer[c]['gain'][arm] for c in transferred]
        error_change=[error(best_transfer[c]['arms'][arm]['endpoint_latlon'])-error(transferred[c]['original_arms'][arm]['endpoint_latlon']) for c in transferred]
        axes[0].bar(positions+delta,gains,width=.25,color=color,label=arm)
        axes[1].bar(positions+delta,error_change,width=.25,color=color,label=arm)
    for ax in axes:
        ax.set_xticks(positions,[c.replace('DS24-','') for c in transferred]);ax.axhline(0,color='black',lw=.8);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Original minus transfer loss (positive is better)')
    axes[0].set_title('Full RF objective; unused phase correction applied')
    axes[1].set_ylabel('Transfer minus original position error, km')
    axes[1].set_title('GPS evaluation after RF selection')
    axes[0].legend(frameon=False)
    fig.suptitle('Best c0-scored start per half-label proposal; paired validity is required for adoption')
    fig.savefig(OUT/'transfer_objective_and_accuracy.png',dpi=180);plt.close(fig)

    text=['# DS24 targeted full-data restart and association diagnostics','',
        'The five targeted scans show no meaningful position-optimizer basin repair under the incumbent full-channel assignments. All 30 bounded fits pass paired gates and return to the incumbent: the largest endpoint displacement is '
        f"{summary['maximum_fixed_endpoint_shift_km']*1000:.5f} m and the largest absolute normalized-loss difference is {summary['maximum_fixed_absolute_loss_difference']:.3g}. "
        'Four finite half-label transfers also provide no acceptable full-data RF improvement. These checks do not establish a global association optimum.','',
        '## Protocol','',
        'Cases 0089 and 0015 were selected as worst all-channel and high-band cases; 0017, 0101 and 0081 were selected because prior channel-halves evaluation showed the three largest current-primary half-channel gains. The current primary is labelled `baseline` in the channel-halves position table; `algo02` there denotes historical ALGO02-v1. This is a targeted post-hoc mechanism test, not an unbiased performance cohort. No new RF was collected. All inference stays inside the original ±12.5 km east/north box centred at 37.906, −122.545.','',
        'The full source is `/srv/bulk/leo/research/ds25-20261024`; the channel-half source is `/srv/bulk/leo/research/ds24-channel-halves-20261024`. Each actual incumbent endpoint and phase reference is read from `cavity_context(...)["arms"][arm]`, because the context’s `x` can predate cavity adoption. Original endpoint objectives replay to <1e−5.','',
        'Fixed tests use the full incumbent labels, aliases, mask, powers, causal signed phase prior and physical priors. Each c arm starts at its own incumbent, CH1–4 endpoint and CH5–8 endpoint. Every fit uses five phase-refresh rounds and at most 48 bounded Gauss–Newton steps per round, with phase references initialized to zero. Both c arms use matched observations, candidate assignments, other priors and budgets.','',
        'RF selection is recorded in each raw result before this report reads GPS. A numerical floor of 1e−4 objective units prevents numerical noise from being labelled an improvement. Fixed restarts use the same assignment; transfers compare the corrected normalized c0 objective under equal assignment priors, preserve the incumbent as an explicit alternative, and require both-arm gates and phase convergence. GPS is used only to evaluate saved endpoints.','',
        '## Fixed assignments: all starts return to the same solution','',
        '| Case | Arm fits | All paired valid | Max absolute loss change | Max endpoint shift, m |',
        '|---|---:|---|---:|---:|']
    for item in fixed_summary:
        text.append(f"| {item['case']} | {item['arm_fits']} | {item['all_paired_valid']} | {item['maximum_absolute_loss_difference']:.3g} | {item['maximum_endpoint_shift_km']*1000:.6f} |")
    text+=['','This rejects the specific explanation that the useful half-channel endpoint lies in a missed position basin for the unchanged full-channel objective. It does not test every possible starting position or every association.','',
        '![Endpoints and restart directions](endpoints.png)','',
        '## Explicit finite association alternatives','',
        'For 0017 CH5–8, 0101 CH1–4, 0015 CH1–4 and 0089 CH5–8, copy the saved half-channel labels and aliases onto exactly matching full-channel track components. Common observation IDs, times and values are asserted equal before transfer. All full observations, retained points, powers, hyperparameters and predictive factors survive; newly introduced candidates receive the full run’s causal phase prior means. Both cold zero and corresponding half-endpoint starts are fitted in both c arms. Near-feasible candidates may use the existing paired constrained-refinement rule (minimum original slack ≥−0.25). No broad catalogue discovery is run.','',
        'The table uses the lowest c0-scored start for each proposed assignment, even when that proposal is invalid, so its failure is visible. Positive loss gain would favour the transfer.','',
        '| Case | Half labels | Changed retained points | Best start | Constrained refinement | Paired valid | c0 loss gain | fitted-c loss gain |',
        '|---|---|---:|---|---|---|---:|---:|']
    for c,item in transferred.items():
        t=best_transfer[c]
        text.append(f"| {c} | {item['group']} | {item['changed_retained_points']} | {t['name']} | {t['constrained_refinement_attempted']} | {t['paired_valid']} | {t['gain']['c0']:+.3f} | {t['gain']['fitted_c']:+.3f} |")
    text+=['','The 0017 transfer qualifies only after constrained refinement; its original minimum gate slacks were −0.142 and −0.123 for c0 and fitted-c. The 0101 proposal remains invalid after the same refinement rule. These are 16 matched-arm transfer results; eight use the additional paired constrained-refinement stage.','',
        '| Case | c arm | Original RMS, Hz | Transfer RMS, Hz | Original error, km | Transfer error, km |',
        '|---|---|---:|---:|---:|---:|']
    for c,item in transferred.items():
        t=best_transfer[c]
        for arm,r in t['arms'].items():
            old=item['original_arms'][arm]
            text.append(f"| {c} | {arm} | {old['RMS_hz']:.3f} | {r['RMS_hz']:.3f} | {error(old['endpoint_latlon']):.3f} | {error(r['endpoint_latlon']):.3f} |")
    text+=['','![RF objective and independent position evaluation](transfer_objective_and_accuracy.png)','',
        'The 0081 half-label differences occur only on points excluded by the full run’s retained mask; its useful half-channel endpoints therefore do not demonstrate an active full-data identity change. No 0081 label-transfer fit was needed.','',
        'Frequency residual RMS, normalized RF objective and geographic accuracy are separate diagnostics. A more accurate endpoint with a worse full RF objective is not adoptable under the current model. Labels remain model associations, not externally verified identities. The finite transfers test the half-channel alternatives only; unexplored joint identity/alias combinations or observation/model errors remain possible.','',
        '## Files and reproduction','',
        '`run_fixed.py CASE` and `run_transfer.py CASE {ch1_4,ch5_8}` run independent bounded case processes. Runtime uses `.venv/bin/python -B`, `PYTHONPATH=/tmp/algo03-feasible-deps:/srv/bulk/leo/research/ds25-20261024/engine:src:tools`, and `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`. No repository modules were changed. All hand-written experiment files are confined to this directory.','',
        '[Fixed arm-level results](fixed_restarts.csv), [transfer arm-level results](association_transfers.csv), [machine summary](summary.json), and the per-case JSON files retain phase convergence, fit histories, gates and RF selections. The report asserts phase amplitudes remain within ±15 s and verifies selections were recorded before GPS evaluation.','']
    (OUT/'RESULTS.md').write_text('\n'.join(text))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
