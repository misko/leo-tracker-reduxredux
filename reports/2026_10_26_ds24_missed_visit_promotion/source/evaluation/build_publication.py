"""Portable report/figures from independently audited post-terminal records."""
import csv
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from audit_implementation import read,write,sha
from scan_statistics import compare,bootstrap
from figures import position_figures,association_frequency,mechanisms


def value(x,digits=1):return 'unavailable' if x is None else f'{x:.{digits}f}'
def percentile(d,key):return value(d[key]) if d.get(key.replace('_m','_finite'),True) else '∞ (unavailable ranks)'


def main():
    data=read(HERE/'analysis_records.json')
    assert data['all_attempts_terminal'] and data['all_results_classified_and_valid_results_audited'] and data['all_protected_hashes_verified']
    assert data['reference_used_only_after_audit_seal']
    protocol=read(HERE/'protocol_v2.json');held=protocol['held_cases'];nom=read(HERE/'nomination_audit.json')
    development=[r['case'] for r in nom['cases'] if r['cohort']=='development'];rows=data['records']
    heldrows=[r for r in rows if r['cohort']=='held'];devrows=[r for r in rows if r['cohort']=='development']
    primary=compare(heldrows,held,'additions_bin_floor');secondary=compare(heldrows,held,'additions_proxy')
    intervals=bootstrap(heldrows,held,['additions_bin_floor','additions_proxy'])
    acq=read(HERE/'all24_acquisition_graph_mechanism.json');caps=read(HERE/'final_cap_audit.json')
    publication=HERE/'publication';publication.mkdir(exist_ok=False);figures=publication/'figures';figures.mkdir()
    for cohort,records,cases in [('held',heldrows,held),('development',devrows,development)]:
        position_figures(records,cases,figures,cohort);association_frequency(records,cases,figures,cohort);mechanisms(acq,records,cases,figures,cohort)
    fields=['case','cohort','variant','arm','eligible_lane','baseline_equivalent','status','valid','read_audit_complete','seconds','error_m',
        'original_GLRT_count','total_GLRT_count','added_native_count','associated_GLRT','association_fraction','frequency_RMS_hz',
        'likelihood_points','curved_likelihood_points','predictive_likelihood_points']
    with (publication/'per_scan.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    lookup={(r['case'],r['variant'],r['arm']):r for r in rows};mechanism_summary={}
    with (publication/'new_native_mechanism.csv').open('x',newline='') as f:
        fields=['case','cohort','observation_id','donor_count','zero_fft_bin','innovation_hz','width_exceeds_wrong_pilot_control','primary_run_valid','in_primary_likelihood']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for candidate in acq['new_native_rows']:
            r=lookup[candidate['case'],'additions_bin_floor','c0'];selected=set(r.get('added_curved_IDs',[])+r.get('added_predictive_IDs',[]))
            writer.writerow(dict(candidate,primary_run_valid=r['valid'],in_primary_likelihood=candidate['observation_id'] in selected if r['valid'] else None))
    for cohort in ('held','development'):
        native=[r for r in acq['new_native_rows'] if r['cohort']==cohort];byid={r['observation_id']:r for r in native}
        completed=[r for r in rows if r['cohort']==cohort and r['variant']=='additions_bin_floor' and r['arm']=='c0' and r['valid']]
        final=[byid[oid] for r in completed for oid in r.get('added_curved_IDs',[])+r.get('added_predictive_IDs',[])]
        from collections import Counter
        mechanism_summary[cohort]=dict(all_native_count=len(native),qualified_primary_scans=len(completed),
            new_curved_likelihood=sum(len(r.get('added_curved_IDs',[])) for r in completed),
            new_predictive_likelihood=sum(len(r.get('added_predictive_IDs',[])) for r in completed),
            final_likelihood_count=len(final),final_zero_fft_bins=sum(r['zero_fft_bin'] for r in final),
            final_donor_distribution=dict(Counter(str(r['donor_count']) for r in final)),
            final_broad_widths=sum(r['width_exceeds_wrong_pilot_control'] for r in final),
            final_scope='available qualified primary runs only; unavailable likelihood is not a measured zero')
    threshold500={arm:{variant:dict(qualified_at_or_below_500m=sum(r['valid'] and r['error_m']<=500 for r in heldrows if r['arm']==arm and r['variant']==variant),intended_scans=len(held)) for variant in ('baseline','additions_bin_floor','additions_proxy')} for arm in ('c0','fitted_c')}
    metrics=dict(primary=primary,secondary_proxy=secondary,bootstrap=intervals,acquisition=acq['groups'],mechanism=mechanism_summary,
        descriptive_500m_counts=threshold500,threshold500m_is_not_a_promotion_gate=True,
        promotion=bool(primary['both_c_arms_pass']),criterion='>=10%lower held cohort median; no p90 increase; no coverage regression; both c arms',
        DS23_unchanged_candidate_compatible=False,scorer_domain_hz=10000000,all_intended_held_scans=12,
        development_not_in_promotion_denominator=True)
    write(publication/'metrics.json',metrics);write(publication/'runtime_caps.json',caps)
    noise_audit=read(HERE/'incumbent_noise_audit.json');write(publication/'incumbent_noise_audit.json',noise_audit)
    title='Promote the frozen 10 MS/s R01 application' if metrics['promotion'] else 'Retain the baseline: the frozen R01 application does not meet promotion criteria'
    lines=['# '+title,'',
        ('The coherent full-bin-floor candidate meets the predeclared held median, p90 and coverage gates in both c arms.' if metrics['promotion'] else
         'The coherent full-bin-floor candidate does not establish the predeclared held median, p90 and coverage requirements in both c arms. Capped and unavailable results remain in the intended cohort; complete-case accuracy cannot substitute for qualification coverage.'),'',
        '| Primary held outcome | c=0 | Fitted c |','|---|---:|---:|']
    for label,fun in [
        ('Audited baseline → treatment scans /12',lambda a:f"{a['baseline_complete']} → {a['treatment_complete']}"),
        ('All-scan median baseline → treatment (m)',lambda a:f"{value(a['baseline']['median_m'])} → {value(a['treatment']['median_m'])}"),
        ('Cohort median improvement',lambda a:'unavailable' if a['cohort_median_improvement'] is None else f"{100*a['cohort_median_improvement']:.2f}%"),
        ('All-scan p90 baseline → treatment (m)',lambda a:('∞' if not a['baseline']['p90_finite'] else value(a['baseline']['p90_m']))+' → '+('∞' if not a['treatment']['p90_finite'] else value(a['treatment']['p90_m']))),
        ('All release gates pass',lambda a:str(a['gate_pass']))]:
        lines.append('|'+label+'|'+'|'.join(fun(primary['arms'][arm]) for arm in ('c0','fitted_c'))+'|')
    lines.append('|Qualified scans at or below 500 m / all intended scans|'+'|'.join(f"{threshold500[arm]['baseline']['qualified_at_or_below_500m']}/12 → {threshold500[arm]['additions_bin_floor']['qualified_at_or_below_500m']}/12" for arm in ('c0','fitted_c'))+'|')
    lines += ['',
        'Infinity denotes conservative unavailable ranks, not a measured infinite geographic error. Median and p90 use all twelve intended scans. A non-finite comparison cannot establish promotion. Six scans have no eligible RF lane and retain baseline-equivalent treatment; they are not positive recovery-transfer examples. The 500 m count and CDF reference line describe the existing accuracy goal, without changing the frozen promotion rule.','',
        'Every numerical run uses the original 25 × 25 km region centered at 37.906, −122.545 and east/north start 0/0, with the full strictly causal TLE catalogue. Observations, candidate identities/aliases, other priors and search budgets are matched between c=0 and fitted c. The reporting-only reference is 37.849061591561885, −122.48574968092912, introduced after terminal/input/read audits; it never seeds inference.','',
        '![Held error distributions and paired scatter](figures/held_error_distributions.png)','',
        '![Held per-scan changes](figures/held_paired_changes.png)','',
        '| Complete-case result (descriptive) | Paired scans | Baseline median (m) | Treatment median (m) | Ratio-of-medians improvement | Median paired relative change |',
        '|---|---:|---:|---:|---:|---:|']
    for variant,result in [('Floor',primary),('Proxy (secondary)',secondary)]:
        for arm in ('c0','fitted_c'):
            a=result['arms'][arm]['complete_cases'];effect=a['cohort_median_improvement'];paired=a['median_paired_relative_change']
            lines.append(f"|{variant}, {arm}|{a['n']}|{value(a['baseline_median_m'])}|{value(a['treatment_median_m'])}|{'unavailable' if effect is None else f'{100*effect:.2f}%'}|{'unavailable' if paired is None else f'{100*paired:.2f}%'}|")
    lines += ['',
        'The ratio of cohort medians is the release estimand; the median of paired percentages is a different descriptive statistic. [Metrics](metrics.json) retain all scan IDs, failures, complete-case denominators and paired-scan bootstrap intervals (10,000 draws, seed 20261026). Interval summaries state their finite-replicate fraction; no GLRT-point bootstrap or secondary-weight selection is used.','',
        '| Held scan | Baseline c=0 (m) | Floor c=0 (m) | Baseline fitted c (m) | Floor fitted c (m) | Eligible RF lane |',
        '|---|---:|---:|---:|---:|---|']
    def cell(case,variant,arm):
        row=lookup[case,variant,arm]
        return value(row['error_m']) if row['valid'] else row['status']
    for case in held:
        lines.append('|'+case+'|'+'|'.join(cell(case,v,a) for v,a in [('baseline','c0'),('additions_bin_floor','c0'),('baseline','fitted_c'),('additions_bin_floor','fitted_c')])+'|'+('yes' if lookup[case,'additions_bin_floor','c0']['eligible_lane'] else 'no; baseline-equivalent')+'|')
    for arm in ('c0','fitted_c'):
        paired=primary['arms'][arm]['scans'];improved=[r for r in paired if r['paired_change_m'] is not None and r['paired_change_m']<0];worsened=[r for r in paired if r['paired_change_m'] is not None and r['paired_change_m']>0]
        text=f"Among audited paired {arm} results, {len(improved)} scans improve and {len(worsened)} regress."
        if improved:
            r=min(improved,key=lambda r:r['paired_change_m']);text+=f" The largest measured gain is {r['case']}, {abs(r['paired_change_m']):.1f} m."
        if worsened:
            r=max(worsened,key=lambda r:r['paired_change_m']);text+=f" The largest measured regression is {r['case']}, {r['paired_change_m']:.1f} m."
        lines += ['',text+' Capped or unaudited pairs have unknown accuracy; they are qualification failures, not measured accuracy regressions.']
    lines += ['',
        'The primary application exactly reproduces the RF-only coherent rule: sparse R01 nominations, top two eligible CH5–8 lanes, earliest curved seed, closed ±12-second blocks, both receivers, original earlier donors only. Position inputs contain originals plus coherent admissions only. R02 and sparse-only unions are excluded. The scope amendment preceded new geographic outcomes.','',
        '| Acquisition and graph accounting | Held 12 | Development 12 |','|---|---:|---:|']
    for label,key in [('Original whole-recording GLRT','original_GLRT_count'),('Original + coherent additions','total_GLRT_count'),('Added native owners','added_native'),('Added in RF graph','new_graph'),('Added actively curved','new_curved')]:
        lines.append(f"|{label}|{acq['groups']['held'][key]}|{acq['groups']['development'][key]}|")
    lines += ['',
        f"The held whole-recording GLRT count increases by {100*acq['groups']['held']['whole_recording_GLRT_count_increase_fraction']:.3f}%. This differs from the earlier sparse-panel10.56% relative CH5–8 coverage gain. Association percentages use the full original-plus-added GLRT denominator, and their numerators include compatible postfit points as well as likelihood points. Frequency RMS uses changed inference support and is not geographic accuracy.",'',
        '![Reserved coherent blocks: original and recovered GLRT points](acquisition_visuals/reserved_glrt_blocks_v2.png)','',
        'Colors in the acquisition figure distinguish new curved RF graph members, other graph members and points outside the graph. They do not encode satellite identity or final likelihood acceptance. The [development blocks](acquisition_visuals/development_glrt_blocks_v3.png) are separately labeled.','',
        '![Association and frequency fit](figures/held_association_frequency.png)','',
        '![Acquisition-to-likelihood mechanism](figures/held_mechanisms.png)','',
        f"Among all 76 held additions, {acq['groups']['held']['zero_fft_bins']} use the zero residual FFT bin, {acq['groups']['held']['one_donor']} have one original donor, and {acq['groups']['held']['broad_widths']} have heuristic widths beyond the wrong-pilot control's 4,500 Hz range. Qualified primary runs accept {mechanism_summary['held']['new_curved_likelihood']} new curved and {mechanism_summary['held']['new_predictive_likelihood']} new predictive likelihood owners; their zero-bin/donor distributions are in [metrics](metrics.json) and the [owner table](new_native_mechanism.csv). Unavailable likelihood membership is not counted as an observed rejection. This is a descriptive mechanism audit, not a new filter or a claim of calibrated independent frequency precision.",'',
        'Graph/noise re-estimation changes incumbent input scales versus baseline in all 11 eligible scans. The [independent noise audit](incumbent_noise_audit.json) verifies, for example, −0.57 to +10.62 Hz in 0077, +1.03 to +9.81 Hz in 0091, and −0.89 to +34.95 Hz in 0010. Floor and proxy have exactly equal incumbent input scales; only new-owner input scales receive the floor. Association paths and likelihood membership may still differ. Attributing a geographic gain specifically to independent added frequencies would require a separate new-owner-only versus frozen-incumbent-weight ablation, which was not introduced into this frozen evaluation.','',
        'Runtime qualification is separate from scientific accuracy. [Runtime/cap accounting](runtime_caps.json) identifies the stage at each cap and retains failed attempts. No partial endpoint is treated as qualified. The original numerical budgets, causal candidates/priors and matched c-arm masks remain fixed; all valid endpoints and inference reads were independently audited before reporting errors.','']
    from collections import Counter
    cap_groups=Counter((lookup[r['case'],'baseline','c0']['cohort'],r['variant'],r.get('active_stage_at_cap','unknown')) for r in caps['rows'])
    lines += ['| Runtime-capped stratum / variant | Active stage at cap | Scans |','|---|---|---:|']
    for (cohort,variant,stage),count in sorted(cap_groups.items()):lines.append(f'|{cohort}, {variant}|{stage}|{count}|')
    lines += ['',
        'The original DS24 inventory has 34 recordings: 24 usable and 10 unavailable. The unavailable members remain an explicit scope limit; no favorable replacement recording is selected. The other 12 usable scans are development evidence, including the reused 0011/0097 examples, and do not enter the promotion denominator. [Development error distributions](figures/development_error_distributions.png), [changes](figures/development_paired_changes.png), [association/RMS](figures/development_association_frequency.png) and [mechanisms](figures/development_mechanisms.png) are labeled separately. All scans were exposed in earlier studies; this is not new-site validation.','',
        'DS23 does not validate this unchanged candidate: all 207 fast recordings are 2.5 MS/s, while the frozen scorer explicitly requires 10 MS/s. Independent metadata checks verify 2,886 segment manifests; 204 recordings retain all original paths and three lack analysis inputs. The 206 adaptive recordings are a different acquisition regime. No resampling, rate-generalized port or DS23 recovery accuracy is claimed. This is an implementation-domain limit, not evidence that sample rate physically causes position error.','',
        '[Per-scan CSV](per_scan.csv) provides errors, qualification, runtime, original/added/associated point counts and RMS. [Provenance](provenance.json) binds evaluation protocols, implementation/source/input audits and terminal receipts. Native IQ and large inference trees remain outside this portable package.']
    with (publication/'README.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    provenance=dict(evaluation_protocol_sha256=sha(HERE/'protocol_v2.json'),analysis_records_sha256=sha(HERE/'analysis_records.json'),
        audits={name:sha(HERE/name) for name in ('nomination_audit.json','ds23_compatibility_audit.json','all24_acquisition_graph_mechanism.json','coherent_candidate_pre_geography_audit.json','candidate_protocol_pre_geography_audit.json','incumbent_noise_audit.json')},
        evaluation_source_hashes={name:sha(HERE/name) for name in ('scan_statistics.py','figures.py','build_publication.py','replay_endpoints.py')},
        independent_no_IQ_or_position_fit_calls=True,terminal_release=data.get('terminal_release',{}))
    write(publication/'provenance.json',provenance)
    files={str(p.relative_to(publication)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in publication.rglob('*') if p.is_file()}
    write(publication/'publication_manifest.json',dict(files=files,total_bytes=sum(r['bytes'] for r in files.values()),promotion=metrics['promotion'],portable_relative_Markdown_links=True))
    print(dict(publication=str(publication),promotion=metrics['promotion'],files=len(files)),flush=True)


if __name__=='__main__':main()
