"""Report-only position evaluation after joint-catalogue RF replay qualifies."""

import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from complete_ds23_excluded_catalogue import prepare
from calibrate_ds23_excluded_catalogue import OUT, ARMS
from run_algo01_ds23_sample import ROOT, read, write, sha


def stats(values):
    a = np.asarray(values)
    return dict(count=len(a), mean_km=float(a.mean()), median_km=float(np.median(a)),
        p90_km=float(np.quantile(a, .9)), maximum_km=float(a.max()), below_half_km=int(np.sum(a<=.5)))


def main():
    protocol = prepare()
    validation = read(OUT/'cohort_verification.json')
    completion = read(OUT/'completed_cohort_audit.json')
    if not completion['qualified'] or not completion['all_terminal']:
        raise ValueError('all initial errors and hypothesis-domain checks must be resolved first')
    if not validation['all_terminal'] or not validation['qualified'] or len(validation['receipts'])!=40:
        raise ValueError('all 40 RF checks must pass before geographic evaluation')
    bindings = {r['case']:r['input_sha256'] for r in validation['receipts']}
    from report_algo02_ds23 import position_error
    from probe_algo03_frame_peak_recovery import SOURCE
    rows, summary = [], {}
    figure, axes = plt.subplots(2, 2, figsize=(14, 9))
    for row, cohort in enumerate(('development', 'confirmation')):
        summary[cohort] = {}
        for column, arm in enumerate(ARMS):
            before, after, accepted = [], [], []
            for case in protocol[cohort+'_cases']:
                path = OUT/case/'result.json'
                if bindings[case][str(path.relative_to(ROOT))]!=sha(path):
                    raise ValueError('verified result changed before evaluation')
                if completion['result_sha256'][case]!=sha(path):
                    raise ValueError('support-completion result changed before evaluation')
                d = read(path)
                old, new = d['incumbent_arms'][arm], d['policy_arms'][arm]
                before.append(position_error(old['endpoint_latlon']))
                after.append(position_error(new['endpoint_latlon']))
                accepted.append(d['accepted'])
                code_gain = d.get('incumbent_code', 0.)-d.get('code', 0.)
                original_node = read(SOURCE/case/'result.json')['final_node']
                changed_rows = sum(a['candidate_index']!=b['candidate_index']
                    for a, b in zip(original_node['seed']['rows'], d.get('selected_node', original_node)['seed']['rows'], strict=True))
                rows.append(dict(case=case, cohort=cohort, arm=arm, accepted=d['accepted'],
                    incumbent_error_km=before[-1], policy_error_km=after[-1],
                    continuous_RF_gain=old['negative_twice_elbo']-new['negative_twice_elbo'],
                    label_code_gain=code_gain, changed_curved_rows=changed_rows,
                    selected_family_changes=len({c['family'] for c in d.get('selected_choices', [])}),
                    selected_index=d.get('selected_index'), selected_stage=d.get('selected_stage'),
                    frequency_RMS_incumbent_hz=old['RMS_hz'], frequency_RMS_trial_hz=new['RMS_hz']))
            summary[cohort][arm] = dict(incumbent=stats(before), policy=stats(after),
                accepted=sum(accepted), improved=sum(b<a-1e-9 for a,b in zip(before,after)),
                worsened=sum(b>a+1e-9 for a,b in zip(before,after)),
                mean_and_median_improve=bool(np.mean(after)<np.mean(before) and np.median(after)<np.median(before)))
            ax = axes[row, column]
            for values, color, label in ((before, 'black', 'Published signed prior'), (after, '#427e9f', 'Excluded-family catalogue search')):
                a = np.sort(values)
                ax.step(np.r_[0,a], np.r_[0,np.arange(1,len(a)+1)/len(a)], where='post', color=color, label=label)
            ax.axvline(.5,color='gray',ls=':')
            ax.set(title=cohort+' · '+arm,xlabel='Position error (km)',ylabel='Fraction of complete cohort',ylim=(0,1.02))
            ax.grid(alpha=.15)
            ax.legend(fontsize=8)
    figure.suptitle('DS23 · fresh causal catalogue search with two families excluded from calibration\n'
        'Whole-family and receiver-split options · original position evidence restored · exact fallback on rejection')
    figure.tight_layout(rect=(0,0,1,.92))
    figure.savefig(OUT/'position_error_distribution.png',dpi=175)
    plt.close(figure)
    with (OUT/'position_comparison.csv').open('w') as handle:
        writer = csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    primary = all(summary[c]['fitted_c']['mean_and_median_improve'] for c in summary)
    write(OUT/'evaluation.json',dict(summary=summary,primary_confirmed=primary,
        goal_achieved=False,count=40,goal_population=413,GPS_used_only_here=True,
        verification_sha256=sha(OUT/'cohort_verification.json'),
        all_original_position_evidence_retained=True, frozen_broader_validation_needed_before_publication=True))
    print(summary,flush=True)
    print('Primary confirmed',primary,flush=True)


if __name__=='__main__':
    main()
