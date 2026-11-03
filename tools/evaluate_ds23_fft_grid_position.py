"""Report-only geographic and frequency-fit evaluation of fixed RF correction."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_fft_grid_position import OUT, prepare
from probe_ds23_fft_grid_origin import OUT as RF
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha


def stats(values):
    return dict(count=len(values),mean_km=float(np.mean(values)),median_km=float(np.median(values)),
                p90_km=float(np.quantile(values,.9)),maximum_km=float(np.max(values)),
                below_half_km=int(np.sum(np.asarray(values)<=.5)))


def main():
    protocol = prepare(); rows = []; summary = {}; null_max = 0.; failures = []
    for cohort in ('development','confirmation'):
        path = OUT/(cohort+'_execution.json')
        if not path.exists():
            continue
        execution = read(path)
        if not execution['all_terminal'] or len(execution['receipts']) != len(protocol[cohort+'_cases']):
            raise ValueError('incomplete cohort')
        errors = [r for r in execution['receipts'] if 'error' in r]
        failures.extend(errors)
        if errors:
            continue
        summary[cohort] = {}
        for arm in ('c0','fitted_c'):
            old = []; new = []; trial = [];null = []
            for case in protocol[cohort+'_cases']:
                r = read(OUT/(case+'.json'))
                for name in ('incumbent','policy','null_cold_refit'):
                    result = r[name+'_arms'][arm]
                    value = position_error(result['endpoint_latlon'])
                    if name == 'incumbent':
                        old.append(value)
                    elif name == 'policy':
                        new.append(value)
                    else:
                        null.append(value)
                trial.append(position_error(r['arms'][arm]['endpoint_latlon']))
                distance = float(np.linalg.norm(np.asarray(r['null_cold_refit_arms'][arm]['endpoint_east_north_km'])-
                                                 r['incumbent_arms'][arm]['endpoint_east_north_km']))
                null_max = max(null_max,distance)
                rows.append(dict(cohort=cohort,case=case,arm=arm,accepted=r['accepted'],
                    incumbent_error_km=old[-1],policy_error_km=new[-1],raw_trial_error_km=trial[-1],
                    error_change_km=new[-1]-old[-1],null_position_difference_km=distance,
                    incumbent_frequency_RMS_hz=r['incumbent_arms'][arm]['RMS_hz'],
                    corrected_trial_frequency_RMS_hz=r['arms'][arm]['RMS_hz'],
                    null_cold_paired_valid=r['null_cold_paired_valid'],
                    changed_original_points=r['measurement_correction']['changed_original_points']))
            rng = np.random.default_rng(2026102063)
            differences = np.asarray(new)-old
            samples = differences[rng.integers(0,len(old),(4000,len(old)))].mean(axis=1)
            summary[cohort][arm] = dict(incumbent=stats(old),policy=stats(new),raw_trial=stats(trial),
                cold_null=stats(null),accepted=sum(r['accepted'] for r in rows if r['cohort']==cohort and r['arm']==arm),
                improved_scans=int(np.sum(differences < -1e-9)),worsened_scans=int(np.sum(differences > 1e-9)),
                mean_error_change_bootstrap_95percent_km=np.quantile(samples,[.025,.975]),
                mean_and_median_improve=bool(np.mean(new)<np.mean(old) and np.median(new)<np.median(old)))
    full = len(summary)==2 and not failures
    primary = full and all(summary[c]['fitted_c']['mean_and_median_improve'] for c in summary)
    all_four = full and all(s['mean_and_median_improve'] for a in summary.values() for s in a.values())
    write(OUT/'evaluation.json',dict(summary=summary,failures=failures,
        primary_confirmed=primary,all_c_arm_metrics_confirmed=all_four,
        maximum_cold_null_position_difference_km=null_max,
        RF_qualification_sha256=sha(RF/'evaluation.json'),protocol_sha256=sha(OUT/'protocol.json'),
        evaluation_source_sha256=sha(ROOT/'tools/evaluate_ds23_fft_grid_position.py'),
        geographic_reference_used_only_here=True,
        no_whole_DS23_claim=True,goal_achieved=False))
    if rows:
        with (OUT/'position_comparison.csv').open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(rows)
        fig,axes=plt.subplots(2,2,figsize=(13,9))
        for row,cohort in enumerate(('development','confirmation')):
            for col,arm in enumerate(('c0','fitted_c')):
                ax=axes[row,col];r=[r for r in rows if r['cohort']==cohort and r['arm']==arm]
                if not r:
                    ax.set_visible(False);continue
                before=np.asarray([v['incumbent_error_km'] for v in r]);after=np.asarray([v['policy_error_km'] for v in r])
                ax.scatter(before,after,c=['#317bb2' if v['accepted'] else '#b8b8b8' for v in r],s=35)
                limit=max(before.max(),after.max())*1.05
                ax.plot([0,limit],[0,limit],color='gray',lw=.8)
                ax.axhline(.5,color='gray',ls=':');ax.axvline(.5,color='gray',ls=':')
                ax.set(xlabel='Signed-prior incumbent error (km)',ylabel='RF-correction policy error (km)',
                       title=f'{cohort} · {arm} · {len(r)} scans')
                s=summary[cohort][arm]
                ax.text(.03,.97,f"Mean {s['incumbent']['mean_km']:.3f} → {s['policy']['mean_km']:.3f} km\n"
                    f"Median {s['incumbent']['median_km']:.3f} → {s['policy']['median_km']:.3f} km\n"
                    f"Original gates accepted {s['accepted']}/{len(r)}",transform=ax.transAxes,va='top',fontsize=9)
                ax.grid(alpha=.15)
        fig.suptitle('DS23 · fixed native CFO grid correction · matched regional cold starts\n'
            'Blue: paired gate pass; gray: unchanged incumbent fallback · position truth used for evaluation only')
        fig.tight_layout(rect=(0,0,1,.92));fig.savefig(OUT/'position_development_confirmation.png',dpi=175);plt.close(fig)
        fig,axes=plt.subplots(2,2,figsize=(14,8))
        for row,cohort in enumerate(('development','confirmation')):
            for col,arm in enumerate(('c0','fitted_c')):
                ax=axes[row,col];r=[r for r in rows if r['cohort']==cohort and r['arm']==arm]
                if not r:
                    ax.set_visible(False);continue
                change=np.array([1000*v['error_change_km'] for v in r])
                ax.bar(range(len(r)),change,color=['#b8b8b8' if not v['accepted'] else
                    '#348653' if v['error_change_km']<0 else '#c45d67' for v in r])
                ax.axhline(0,color='black',lw=.7)
                ax.set(xticks=range(len(r)),xticklabels=[v['case'].split('-')[-1] for v in r],
                    ylabel='Position error change (m; negative improves)',xlabel='DS23 scan',title=f'{cohort} · {arm}')
                ax.tick_params(axis='x',rotation=60,labelsize=7);ax.grid(axis='y',alpha=.15)
        fig.suptitle('Fixed RF correction: individual position effects\n'
            'Both c arms preserve observations and physical priors · failed paired gates retain incumbent')
        fig.tight_layout(rect=(0,0,1,.92));fig.savefig(OUT/'position_error_changes.png',dpi=175);plt.close(fig)
    print({c:{a:{k:s[k] for k in ('incumbent','policy','accepted','mean_and_median_improve')} for a,s in v.items()}
           for c,v in summary.items()},flush=True)
    print('Primary confirmed',primary,'all-c confirmed',all_four,'cold-null max km',null_max,flush=True)


if __name__ == '__main__':
    main()
