"""Exact discrete-prior control on already independently replayed RF fits."""

import argparse
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_unknown_catalogue_prior import corrected_cost
from probe_ds23_unknown_polynomial import OUT as ORIGINAL,ARMS
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_unknown_catalogue_prior'


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    sources={n:sha(ROOT/'tools'/n) for n in ('ds23_unknown_catalogue_prior.py','probe_ds23_unknown_catalogue_prior.py')}
    if path.exists():
        p=read(path)
        if p['source_sha256']!=sources:
            raise ValueError('catalogue category prior sources changed')
        return p
    previous=read(ORIGINAL/'protocol.json');audit=read(ORIGINAL/'cohort_verification.json')
    if not audit['qualified'] or len(audit['receipts'])!=40:
        raise ValueError('all original numerical fits must be independently replayed first')
    p=dict(development_cases=previous['development_cases'],confirmation_cases=previous['confirmation_cases'],
        source_sha256=sources,RF_verification_sha256=sha(ORIGINAL/'cohort_verification.json'),
        hypothesis='unknown and named identities must pay their normalized catalogue category probabilities',
        prior='each frozen family slot unknown probability .05, otherwise uniform among all N causal catalogue entries',
        exact_cost_change='subtract 2*k*log(N) from previous conditional-name cost; no position or nuisance refit needed',
        same_six_candidates_and_nulls=True,ranking_within_single_and_pair_nominee_pools_unchanged=True,
        original_all_observation_likelihoods_and_paired_gates_unchanged=True,
        original_partition_and_alias_branches_conditioned_not_marginalized=True,
        not_a_full_catalogue_or_partition_posterior=True,
        selection='both coded gains >2log2 versus better valid saved/cold null; lowest c0 cost',
        no_GPS_future_TLE_new_RF_or_current_frequency_used_to_set_discrete_prior=True,
        original_baseline_GPS_exposed_but_unknown_trial_position_errors_not_used_for_selection=True,
        primary='fitted-c mean AND median improve in both cohorts; report c0',goal_population=413)
    write(path,p);return p


def decisions():
    p=prepare();audit=read(ORIGINAL/'cohort_verification.json')
    bindings={r['case']:r for r in audit['receipts']};rows=[]
    for case in p['development_cases']+p['confirmation_cases']:
        path=ORIGINAL/case/'result.json'
        if sha(path)!=bindings[case]['result_sha256']:
            raise ValueError('verified numerical fits changed')
        r=read(path);elements_path=SOURCE/case/'nominal_elements.json';elements=read(elements_path)
        cutoff=read(SOURCE/case/'receipt.json')['cutoff_utc_ns']
        if any(max(e['provenance']['element_epoch_utc_ns'],e['provenance']['collected_utc_ns'])>cutoff for e in elements.values()):
            raise ValueError('future catalogue identity')
        n=len(elements);trials=[]
        for k,t in enumerate(r['trials'][1:],1):
            cost={a:corrected_cost(t['arms'][a]['negative_twice_elbo'],n,len(t['unknown_families'])) for a in ARMS}
            gains={a:r['reference_costs'][a]-cost[a] for a in ARMS}
            trials.append(dict(original_trial_index=k,unknown_families=t['unknown_families'],
                paired_valid=t['paired_valid'],catalogue_costs=cost,gains=gains,
                eligible=bool(t['paired_valid'] and min(gains.values())>2*np.log(2))))
        eligible=[t for t in trials if t['eligible']]
        winner=min(eligible,key=lambda t:t['catalogue_costs']['c0']) if eligible else None
        row=dict(case=case,catalogue_count=n,accepted=winner is not None,
            selected_trial_index=winner['original_trial_index'] if winner else None,
            selected_unknown_families=winner['unknown_families'] if winner else [],trials=trials,
            original_result_sha256=sha(path),elements_sha256=sha(elements_path),no_GPS_used=True)
        write(OUT/(case+'.json'),row);rows.append(row)
    write(OUT/'decisions.json',dict(rows=rows,all_terminal=True,no_GPS_used=True,
        accepted_count=sum(r['accepted'] for r in rows)))
    print('Catalogue-aware adopted',sum(r['accepted'] for r in rows),'of',len(rows),flush=True)


def evaluate():
    protocol=prepare();d=read(OUT/'decisions.json')
    if not d['all_terminal'] or len(d['rows'])!=40:
        raise ValueError('all decisions must be sealed before geographic evaluation')
    from report_algo02_ds23 import position_error
    rows=[];results={};fig,axes=plt.subplots(2,2,figsize=(13,9))
    for row,cohort in enumerate(('development','confirmation')):
        results[cohort]={}
        for col,arm in enumerate(ARMS):
            before=[];after=[]
            for decision in d['rows']:
                case=decision['case']
                if case not in protocol[cohort+'_cases']:continue
                path=ORIGINAL/case/'result.json'
                if sha(path)!=decision['original_result_sha256']:raise ValueError('numerical fit changed')
                r=read(path);original=r['incumbent_arms'][arm]
                chosen=r['trials'][decision['selected_trial_index']]['arms'][arm] if decision['accepted'] else original
                before.append(position_error(original['endpoint_latlon']));after.append(position_error(chosen['endpoint_latlon']))
                rows.append(dict(case=case,cohort=cohort,arm=arm,accepted=decision['accepted'],
                    unknown_norads=','.join(str(r['norad_by_label'][str(j)]) for j in decision['selected_unknown_families']),
                    incumbent_error_km=before[-1],policy_error_km=after[-1]))
            results[cohort][arm]=dict(incumbent_mean_km=float(np.mean(before)),incumbent_median_km=float(np.median(before)),
                policy_mean_km=float(np.mean(after)),policy_median_km=float(np.median(after)),
                mean_and_median_improve=bool(np.mean(after)<np.mean(before) and np.median(after)<np.median(before)))
            ax=axes[row,col]
            for values,color,label in ((before,'black','Published signed prior'),(after,'#ac6a38','Catalogue-aware unknown policy')):
                v=np.sort(values);ax.step(np.r_[0,v],np.r_[0,np.arange(1,len(v)+1)/len(v)],where='post',color=color,label=label)
            ax.axvline(.5,color='gray',ls=':');ax.grid(alpha=.15);ax.legend(fontsize=8)
            ax.set(title=cohort+' · '+arm,xlabel='Position error (km)',ylabel='Fraction of complete cohort',ylim=(0,1.02))
    fig.suptitle('DS23 · catalogue-aware unknown category prior\nExact prior-only reweighting; same verified RF fits, original observations and paired gates')
    fig.tight_layout(rect=(0,0,1,.92));fig.savefig(OUT/'position_error_distribution.png',dpi=175);plt.close(fig)
    primary=all(results[c]['fitted_c']['mean_and_median_improve'] for c in results)
    write(OUT/'evaluation.json',dict(results=results,primary_confirmed=primary,goal_achieved=False,
        decisions_sha256=sha(OUT/'decisions.json'),GPS_used_only_here=True,
        accepted_rows=[r for r in rows if r['accepted']],goal_population=413))
    with (OUT/'position_comparison.csv').open('w') as handle:
        w=csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    print('Primary',primary,'results',results,'changed',[r for r in rows if r['accepted']],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('decide','evaluate'),required=True)
    decisions() if parser.parse_args().stage=='decide' else evaluate()
