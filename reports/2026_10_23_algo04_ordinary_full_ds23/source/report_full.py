"""Reporting-only GPS evaluation of frozen DS23 ordinary graph results."""
import argparse
import csv
import hashlib
import json
import math
import statistics
import random
from pathlib import Path

OUT = Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023')
PRIOR = Path('/srv/bulk/leo/research/algo04-candidate-20261023')
MANIFEST = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_19_algo02_ds23_full/sample.json')
ARMS = ('c0', 'fitted_c')
METHODS = ('reference', 'rejected_candidate', 'ordinary')
LABELS = {'reference':'Published reference', 'rejected_candidate':'Prior rejected candidate', 'ordinary':'Ordinary graph + native'}
ARM_LABELS = {'c0':'c = 0', 'fitted_c':'Fitted c'}
REFERENCE = (37.849061591561885, -122.48574968092912)


def position_error(point):
    a, b = map(math.radians, (point[0], REFERENCE[0]))
    h = math.sin((a-b)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(point[1]-REFERENCE[1])/2)**2
    return 12742*math.asin(math.sqrt(max(0., min(1., h))))


def read(path):
    return json.loads(path.read_text())


def quantile(values, p):
    values = sorted(values)
    j = (len(values)-1)*p
    return values[math.floor(j)] + (values[math.ceil(j)]-values[math.floor(j)])*(j-math.floor(j))


def metrics(rows, population):
    values = [r['error_km'] for r in rows if r['error_km'] is not None]
    result = dict(localized=len(values), population=population, unlocalized_or_missing=population-len(values),
                  search_completed=sum(r.get('search_complete',False) for r in rows),
                  inherited_carries=sum(r.get('source_status') in ('reference_unqualified','frozen_bank_incomplete') for r in rows),
                  execution_fallbacks=sum(r.get('source_status')=='execution_fallback' for r in rows),
                  failed_fits=sum(r.get('source_status') in ('failed','error','execution_failed') for r in rows),
                  missing_or_pending=sum(r.get('source_status') in ('missing','pending') for r in rows))
    result.update({k: None for k in ('mean_km', 'median_km', 'p90_km', 'p95_km', 'worst_km')})
    if values:
        result.update(mean_km=statistics.mean(values), median_km=statistics.median(values),
                      p90_km=quantile(values, .9), p95_km=quantile(values, .95), worst_km=max(values))
    valid = [r for r in rows if r['associated_points'] is not None]
    associated = sum(r['associated_points'] for r in valid)
    total = sum(r['all_GLRT'] for r in valid)
    result.update(associated_unique_original_IDs=associated, all_GLRT=total,
                  coverage_scans=len(valid), associated_percent=100*associated/total if total else None,
                  within_half_km_full_fraction=sum(v <= .5 for v in values)/population if population else None)
    return result


def coverage(cov):
    ids = cov.get('accepted_observation_ids', cov.get('associated_original_ids'))
    if ids is None:
        raise ValueError('coverage lacks original observation IDs')
    unique = len(set(ids))
    if unique != len(ids) or unique != cov['associated'] or not 0 <= unique <= cov['total_GLRT']:
        raise ValueError('coverage original ID count is inconsistent')
    return unique, cov['total_GLRT']


def build_rows(members, results, prior):
    rows, statuses = [], []
    for member in members:
        case = member['dataset_label']
        current, old = results.get(case), prior.get(case)
        status = (current or {}).get('status', 'missing')
        graph=(current or {}).get('ordinary_graph') or {}
        statuses.append(dict(case=case, status=status, reason=(current or {}).get('reason'),
                             selected_name=graph.get('selected_name'), reference_fallback=graph.get('reference_fallback'),
                             search_complete=bool((current or {}).get('search_complete',status=='complete')),
                             prior_source_status=(old or {}).get('status','missing'),
                             failed_stage=(current or {}).get('failed_stage'), error=(current or {}).get('error'),
                             timing=(current or {}).get('timing', (current or {}).get('seconds'))))
        views = {'reference': (current or {}).get('reference', (old or {}).get('reference')),
                 'rejected_candidate': (old or {}).get('candidate'), 'ordinary': (current or {}).get('final')}
        for method, view in views.items():
            for arm in ARMS:
                source_status=status if method=='ordinary' else ((old or {}).get('status','missing') if method=='rejected_candidate' else ('available' if view else 'missing'))
                row = dict(case=case, cohort='fast' if member['recording_format']=='short_window_iq_recording' else 'adaptive',
                           captured_utc_ns=member.get('captured_utc_ns'), method=method, arm=arm, status=status if method=='ordinary' else ('available' if view else 'missing'),
                           source_status=source_status,
                           search_complete=bool((current or {}).get('search_complete',status=='complete')) if method=='ordinary' else (source_status=='complete' if method=='rejected_candidate' else view is not None),
                           error_km=None, RMS_hz=None, associated_points=None, all_GLRT=None, associated_percent=None)
                # A failed computation must never silently become an accepted localization.
                failed = method == 'ordinary' and status in ('failed', 'error', 'execution_failed', 'missing', 'pending')
                fit = (view or {}).get('arms', {}).get(arm)
                if fit and not failed:
                    point = fit.get('endpoint_latlon')
                    if point is None or len(point)!=2 or not all(math.isfinite(v) for v in point):
                        raise ValueError(f'nonfinite position: {case}/{method}/{arm}')
                    associated, total = coverage(view['coverage'][arm])
                    row.update(error_km=position_error(point), RMS_hz=fit.get('RMS_hz'), associated_points=associated,
                               all_GLRT=total, associated_percent=100*associated/total if total else None)
                rows.append(row)
    return rows, statuses


def comparisons(rows):
    index = {(r['case'],r['method'],r['arm']):r for r in rows}
    result = []
    for r in rows:
        if r['method']!='ordinary' or r['error_km'] is None:
            continue
        for baseline in ('reference', 'rejected_candidate'):
            before = index[r['case'],baseline,r['arm']]
            if before['error_km'] is None:
                continue
            result.append(dict(case=r['case'], cohort=r['cohort'], captured_utc_ns=r['captured_utc_ns'], arm=r['arm'], baseline=baseline,
                               baseline_error_km=before['error_km'], ordinary_error_km=r['error_km'],
                               delta_error_km=r['error_km']-before['error_km'],
                               delta_RMS_hz=r['RMS_hz']-before['RMS_hz'] if r['RMS_hz'] is not None and before['RMS_hz'] is not None else None,
                               delta_associated_points=r['associated_points']-before['associated_points']))
    return result


def block_intervals(changes, draws=2000):
    """Circular chronological blocks: sensitivity to dependence, not new-site inference."""
    result=[]
    for arm in ARMS:
        cc=sorted((r for r in changes if r['arm']==arm and r['baseline']=='reference'),
                  key=lambda r:(r['captured_utc_ns'] or 0,r['case']))
        n=len(cc)
        if not n: continue
        for length in (10,20):
            rng=random.Random(2026102304);mean=[];median=[]
            for _ in range(draws):
                indices=[]
                while len(indices)<n:
                    start=rng.randrange(n);indices.extend((start+j)%n for j in range(length))
                sample=[cc[i] for i in indices[:n]]
                mean.append(statistics.mean(r['delta_error_km'] for r in sample))
                median.append(statistics.median(r['ordinary_error_km'] for r in sample)-statistics.median(r['baseline_error_km'] for r in sample))
            for metric,vv in (('mean',mean),('median',median)):
                result.append(dict(arm=arm,block_scans=length,metric=metric,paired_scans=n,
                                   lower_delta_km=quantile(vv,.025),upper_delta_km=quantile(vv,.975)))
    return result


def promotion(rows, changes, expected_cases=None, audit_passed=None):
    result={}
    for arm in ARMS:
        cc=[r for r in changes if r['arm']==arm and r['baseline']=='reference']
        before=[r['baseline_error_km'] for r in cc];after=[r['ordinary_error_km'] for r in cc]
        result[arm]=dict(mean_improves=bool(cc) and statistics.mean(after)<statistics.mean(before),
                         median_improves=bool(cc) and statistics.median(after)<statistics.median(before),
                         p95_does_not_increase=bool(cc) and quantile(after,.95)<=quantile(before,.95)+1e-9,
                         worst_does_not_increase=bool(cc) and max(after)<=max(before)+1e-9,
                         no_regression_above_half_km=bool(cc) and max(r['delta_error_km'] for r in cc)<=.5)
    ordinary=[r for r in rows if r['method']=='ordinary']
    result['all_scientific_completed']=bool(ordinary) and all(r['search_complete'] for r in ordinary)
    expected=set(expected_cases) if expected_cases is not None else {r['case'] for r in ordinary}
    allowed={'DS23-0068':'reference_unqualified','DS23-0004':'frozen_bank_incomplete'}
    cases={r['case'] for r in ordinary}
    result['all_planned_cases_terminal']=bool(expected) and cases==expected and all(r['source_status'] not in ('missing','pending') for r in ordinary)
    result['no_new_execution_fallback']=all(r['source_status']!='execution_fallback' for r in ordinary)
    result['only_expected_inherited_exceptions']=all(r['source_status']=='complete' or allowed.get(r['case'])==r['source_status'] for r in ordinary)
    result['numerical_QA_audit_passed']=audit_passed
    operational=all(result[k] for k in ('all_planned_cases_terminal','no_new_execution_fallback','only_expected_inherited_exceptions'))
    result['computational_eligibility']=False if not operational else audit_passed
    performance=all(all(result[a].values()) for a in ARMS)
    result['performance_requirements_passed']=performance
    result['eligible']=None if audit_passed is None else bool(operational and performance and audit_passed)
    result['decision_status']='provisional_pending_numerical_QA' if audit_passed is None else ('eligible' if result['eligible'] else 'not_eligible')
    return result


def summaries(rows):
    result = []
    for cohort in ('all','fast','adaptive'):
        selected = [r for r in rows if cohort=='all' or r['cohort']==cohort]
        population = len({r['case'] for r in selected})
        common = {r['case'] for r in selected if r['error_km'] is not None}
        common = {c for c in common if all(any(r['case']==c and r['method']==m and r['arm']==a and r['error_km'] is not None and r['search_complete'] for r in selected) for m in METHODS for a in ARMS)}
        for mode in ('full_denominator', 'common_completed'):
            for method in METHODS:
                for arm in ARMS:
                    rr = [r for r in selected if r['method']==method and r['arm']==arm and (mode=='full_denominator' or r['case'] in common)]
                    result.append(dict(cohort=cohort, comparison_cohort=mode, method=method, arm=arm,
                                       **metrics(rr, population if mode=='full_denominator' else len(common))))
    return result


def ablations(rows):
    index = {(r['case'],r['method'],r['arm']):r for r in rows}
    result=[]
    for r in rows:
        if r['arm']!='c0' or r['error_km'] is None:
            continue
        fitted=index[r['case'],r['method'],'fitted_c']
        if fitted['error_km'] is not None:
            result.append(dict(case=r['case'],cohort=r['cohort'],method=r['method'],
                               fitted_minus_c0_error_km=fitted['error_km']-r['error_km'],
                               fitted_minus_c0_RMS_hz=fitted['RMS_hz']-r['RMS_hz'] if fitted['RMS_hz'] is not None and r['RMS_hz'] is not None else None))
    return result


def write_table(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def figures(out, rows, changes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes=plt.subplots(3,2,figsize=(12,13),layout='constrained')
    for col, arm in enumerate(ARMS):
        for method in METHODS:
            vv=sorted(r['error_km'] for r in rows if r['method']==method and r['arm']==arm and r['error_km'] is not None)
            if vv:
                for row in (0,1): axes[row,col].plot(vv,[(i+1)/len(vv) for i in range(len(vv))],label=f'{LABELS[method]} (n={len(vv)})')
        for row in (0,1): axes[row,col].set(xlabel='Position error (km)',ylabel='CDF of localized scans',title=ARM_LABELS[arm]+(' · 0–5 km detail' if row==0 else ' · full range'))
        axes[0,col].set_xlim(0,5)
        cc=[r for r in changes if r['arm']==arm and r['baseline']=='reference']
        axes[2,col].scatter([r['baseline_error_km'] for r in cc],[r['ordinary_error_km'] for r in cc],s=12)
        limit=max([r[k] for r in cc for k in ('baseline_error_km','ordinary_error_km')]+[1])
        axes[2,col].plot([0,limit],[0,limit],'k--',lw=.7)
        axes[2,col].set(xlabel='Published reference error (km)',ylabel='Ordinary graph + native error (km)',title=ARM_LABELS[arm])
        axes[0,col].legend(fontsize=8)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('Reported policy positions, including explicit reference carries · missing results remain in summary denominators')
    fig.savefig(out/'distributions_and_pairs.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,10),layout='constrained')
    for col,arm in enumerate(ARMS):
        cc=[r for r in changes if r['arm']==arm and r['baseline']=='reference']
        top=sorted(sorted(cc,key=lambda r:abs(r['delta_error_km']),reverse=True)[:20],key=lambda r:r['delta_error_km'])
        axes[0,col].barh(range(len(top)),[r['delta_error_km'] for r in top],color=['#1b9e77' if r['delta_error_km']<0 else '#d73027' for r in top])
        axes[0,col].axvline(0,c='black',lw=.7)
        axes[0,col].set_yticks(range(len(top)),[r['case'] for r in top],fontsize=7)
        axes[0,col].set(xlabel='Ordinary minus reference error (km)',title=ARM_LABELS[arm]+' · green improves, red regresses')
        for method in METHODS:
            rr=[r for r in rows if r['arm']==arm and r['method']==method and r['error_km'] is not None]
            axes[1,col].scatter([r['associated_percent'] for r in rr],[r['error_km'] for r in rr],s=10,alpha=.6,label=LABELS[method])
        axes[1,col].set(xlabel='Unique original GLRT associated (%)',ylabel='Position error (km)')
        axes[1,col].legend(fontsize=8)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.savefig(out/'worst_changes_and_association.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for row,cohort in enumerate(('fast','adaptive')):
        for col,arm in enumerate(ARMS):
            ax=axes[row,col]
            for k,method in enumerate(METHODS):
                rr=[r for r in rows if r['cohort']==cohort and r['arm']==arm and r['method']==method]
                s=metrics(rr,len(rr));keys=('mean_km','median_km','p90_km','p95_km','worst_km')
                xx=[j+(k-1)*.24 for j in range(5)]
                ax.bar(xx,[s[key] or 0 for key in keys],width=.23,label=f'{LABELS[method]} ({s["localized"]}/{s["population"]})')
            ax.set_xticks(range(5),['Mean','Median','90th percentile','95th percentile','Worst'])
            ax.set(ylabel='Position error (km)',title=f'{cohort.capitalize()} recordings · {ARM_LABELS[arm]}')
            ax.grid(axis='y',alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Recording-format distributions · legend shows localized / full manifest denominator')
    fig.savefig(out/'recording_formats.png',dpi=150);plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    parser.add_argument('--prior',type=Path,default=PRIOR);parser.add_argument('--manifest',type=Path,default=MANIFEST)
    parser.add_argument('--audit',type=Path,help='Independent numerical QA JSON with all_passed boolean; omission leaves QA provisional')
    args=parser.parse_args();out=args.out
    members=read(args.manifest)['selected']
    current={};prior={};hashes={}
    for member in members:
        case=member['dataset_label']
        for root, target in ((out,current),(args.prior,prior)):
            path=root/'raw'/case/'result.json'
            if path.exists():
                target[case]=read(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    rows,statuses=build_rows(members,current,prior);changes=comparisons(rows);summary=summaries(rows)
    protocol=read(out/'protocol.json') if (out/'protocol.json').exists() else {'cases':sorted(prior)}
    planned=set(protocol['cases'])
    available_summary=summaries([r for r in rows if r['case'] in planned])
    for r in summary:r['population_scope']='full_manifest'
    for r in available_summary:r['population_scope']='planned_available'
    summary.extend(available_summary)
    for name in ('tables','figures','evidence'):(out/name).mkdir(parents=True,exist_ok=True)
    for name,data in (('positions',rows),('execution_status',statuses),('summary',summary),('paired_changes',changes),('c_ablation',ablations(rows))):
        write_table(out/'tables'/f'{name}.csv',data)
    regressions=[]
    for cohort in ('all','fast','adaptive'):
        for arm in ARMS:
            for baseline in ('reference','rejected_candidate'):
                cc=[r for r in changes if r['arm']==arm and r['baseline']==baseline and (cohort=='all' or r['cohort']==cohort)]
                regressions.append(dict(cohort=cohort,arm=arm,baseline=baseline,paired_scans=len(cc),
                                        regressions_above_half_km=sum(r['delta_error_km']>.5 for r in cc),
                                        regressions_above_1km=sum(r['delta_error_km']>1 for r in cc)))
    write_table(out/'tables/regressions.csv',regressions);figures(out/'figures',rows,changes)
    write_table(out/'tables/block_intervals.csv',block_intervals(changes))
    audit=read(args.audit) if args.audit else None
    audit_passed=None if audit is None else audit.get('all_passed',audit.get('QA_audit_passed'))
    if audit is not None and not isinstance(audit_passed,bool):raise ValueError('independent QA receipt must contain all_passed boolean')
    receipt=dict(GPS_only_in_report=True,population=len(members),result_hashes=hashes,
                 independent_audit_path=str(args.audit) if args.audit else None,
                 independent_audit_sha256=hashlib.sha256(args.audit.read_bytes()).hexdigest() if args.audit else None,
                 planned_available_population=len(planned),promotion=promotion([r for r in rows if r['case'] in planned],changes,planned,audit_passed),
                 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),summaries=summary,regressions=regressions)
    (out/'evidence/report_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    text=['# Full DS23 ordinary graph-fit evaluation','',
          f'Frozen result evaluation over {len(members)} manifest recordings. Missing and failed results remain in the full denominator. Common completed cohorts require all three methods and both c arms.',
          '', 'Coverage counts unique accepted original observation IDs per recording. Frequency RMS and position accuracy are separate outcomes; lower in-sample RMS does not establish better localization.',
          '', 'The paired c=0 versus fitted-c table reports frequency RMS and position-error changes independently. Matched observation, candidate, prior and budget controls must be verified from runner provenance.',
          '', '[Summary distributions](tables/summary.csv) · [Regressions](tables/regressions.csv) · [Status and fallbacks](tables/execution_status.csv) · [Paired c ablation](tables/c_ablation.csv)',
          '', f'Planned available population: {len(planned)}. Full-manifest and planned-available denominators are reported separately. Reference-unqualified, incomplete-bank and execution-fallback positions are retained as explicit reference carries, and excluded from the common scientific-completion cohort.',
          '', 'Scientific-search completion is descriptive, separate from the frozen computational promotion condition: all planned cases terminal, no new execution fallback, only the two declared inherited exceptions, and valid numerical QA. An omitted independent QA receipt leaves this condition provisional. The five performance checks retain their frozen thresholds.',
          '', 'Promotion checks: `'+json.dumps(receipt['promotion'],sort_keys=True)+'`.',
          '', 'Chronological circular moving-block intervals (10 and 20 scans) measure sensitivity to within-corpus dependence; they do not establish generalization to new locations.',
          '', '![Distributions and paired errors](figures/distributions_and_pairs.png)', '', '![Largest changes and coverage](figures/worst_changes_and_association.png)', '']
    text.extend(['![Fast and adaptive distributions](figures/recording_formats.png)',''])
    (out/'REPORT.md').write_text('\n'.join(text))


if __name__=='__main__':
    main()
