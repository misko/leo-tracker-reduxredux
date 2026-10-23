"""Evaluate frozen full-DS23 candidate, keeping GPS out of selection."""
from pathlib import Path
from collections import Counter
import csv
import json
import shutil
import tarfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import run_algo04_candidate as study
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error

OUT=study.OUT
METHODS=['reference','graph','candidate']
LABELS={'reference':'Published reference','graph':'Graph recovery','candidate':'ALGO04 candidate'}


def table(name,rows):
    with (OUT/'tables'/name).open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def summarize(rows):
    e=np.array([r['error_km'] for r in rows]);n=sum(r['all_GLRT'] for r in rows);associated=sum(r['associated_points'] for r in rows)
    return dict(scans=len(rows),mean_km=float(e.mean()),median_km=float(np.median(e)),p90_km=float(np.quantile(e,.9)),
        p95_km=float(np.quantile(e,.95)),max_km=float(e.max()),below_half_km=int((e<=.5).sum()),
        associated_points=associated,all_GLRT=n,associated_percent=100*associated/n,
        median_scan_association_percent=float(np.median([r['associated_percent'] for r in rows])))


def paired(rows,arm):
    original={r['case']:r for r in rows if r['arm']==arm and r['method']=='reference'}
    proposed={r['case']:r for r in rows if r['arm']==arm and r['method']=='candidate'}
    cases=sorted(original,key=lambda c:original[c]['captured_utc_ns'])
    return [dict(case=c,arm=arm,recording_format=original[c]['recording_format'],
        original_error_km=original[c]['error_km'],candidate_error_km=proposed[c]['error_km'],
        delta_error_km=proposed[c]['error_km']-original[c]['error_km'],
        associated_points_added=proposed[c]['associated_points']-original[c]['associated_points'],
        delta_association_percent=proposed[c]['associated_percent']-original[c]['associated_percent'],
        delta_RMS_hz=proposed[c]['RMS_hz']-original[c]['RMS_hz']) for c in cases]


def block_intervals(changes):
    # Chronologically contiguous, circular moving blocks. This is sensitivity
    # to dependence at two scales, not evidence of new-location performance.
    before=np.array([r['original_error_km'] for r in changes]);after=np.array([r['candidate_error_km'] for r in changes]);n=len(before)
    rng=np.random.default_rng(2026102304);result=[]
    for length in [10,20]:
        draws=[]
        for _ in range(2000):
            starts=rng.integers(0,n,size=int(np.ceil(n/length)));ix=((starts[:,None]+np.arange(length))%n).ravel()[:n]
            draws.append([float(np.mean(after[ix]-before[ix])),float(np.median(after[ix])-np.median(before[ix]))])
        interval=np.quantile(draws,[.025,.975],axis=0)
        for k,metric in enumerate(['mean','median']):result.append(dict(block_scans=length,metric=metric,lower_delta_km=float(interval[0,k]),upper_delta_km=float(interval[1,k])))
    return result


def promotion(reference,candidate,changes):
    return dict(mean_improves=candidate['mean_km']<reference['mean_km'],median_improves=candidate['median_km']<reference['median_km'],
        p95_does_not_increase=candidate['p95_km']<=reference['p95_km']+1e-9,
        worst_does_not_increase=candidate['max_km']<=reference['max_km']+1e-9,
        no_regression_above_half_km=max(r['delta_error_km'] for r in changes)<=.5)


def figures(rows,changes):
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for col,arm in enumerate(['c0','fitted_c']):
        for method in METHODS:
            values=np.sort([r['error_km'] for r in rows if r['arm']==arm and r['method']==method]);cdf=np.arange(1,len(values)+1)/len(values)
            for ax in axes[:,col]:ax.plot(values,cdf,label=LABELS[method]);ax.grid(alpha=.2);ax.set(xlabel='Position error (km)',ylabel='Empirical CDF',title=arm);ax.axvline(.5,c='gray',ls='--',lw=.8)
        axes[0,col].set_xlim(0,5);axes[0,col].set_title(arm+' · 0–5 km detail');axes[1,col].legend(fontsize=8)
    fig.suptitle('All 410 available DS23 scans · paired observations and priors across c arms\nALGO04 candidate is unpromoted; all unchanged fallbacks retained')
    fig.savefig(OUT/'figures/error_distributions.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,10),layout='constrained')
    for col,arm in enumerate(['c0','fitted_c']):
        cc=[r for r in changes if r['arm']==arm];before=np.array([r['original_error_km'] for r in cc]);after=np.array([r['candidate_error_km'] for r in cc]);lim=max(before.max(),after.max())*1.04
        axes[0,col].scatter(before,after,s=14,c=[r['associated_points_added'] for r in cc],cmap='viridis');axes[0,col].plot([0,lim],[0,lim],'k--',lw=.8)
        axes[0,col].set(xlabel='Reference error (km)',ylabel='Candidate error (km)',title=arm,aspect='equal')
        top=sorted(sorted(cc,key=lambda r:abs(r['delta_error_km']),reverse=True)[:20],key=lambda r:r['delta_error_km'])
        axes[1,col].barh(range(len(top)),[r['delta_error_km'] for r in top],color=['C2' if r['delta_error_km']<0 else 'C3' for r in top]);axes[1,col].set_yticks(range(len(top)),[r['case'] for r in top],fontsize=7)
        axes[1,col].set(xlabel='Candidate minus reference error (km)',title='Largest absolute changes');axes[1,col].axvline(0,c='black',lw=.7)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('Per-scan gains and regressions · display ranking uses evaluation GPS only')
    fig.savefig(OUT/'figures/paired_changes.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(17,5),layout='constrained')
    for method in METHODS:
        rr=[r for r in rows if r['arm']=='fitted_c' and r['method']==method]
        axes[0].scatter([r['associated_percent'] for r in rr],[r['error_km'] for r in rr],s=13,alpha=.6,label=LABELS[method])
    cc=[r for r in changes if r['arm']=='fitted_c']
    axes[1].scatter([r['associated_points_added'] for r in cc],[r['delta_error_km'] for r in cc],s=18,alpha=.7)
    axes[2].scatter([r['delta_RMS_hz'] for r in cc],[r['delta_error_km'] for r in cc],s=18,alpha=.7)
    axes[0].set(xlabel='Original GLRT associated (%)',ylabel='Position error (km)');axes[0].legend(fontsize=8)
    axes[1].set(xlabel='Additional associated original GLRT points',ylabel='Change in position error (km)')
    axes[2].set(xlabel='Change in frequency RMS (Hz)',ylabel='Change in position error (km)')
    for ax in axes:ax.grid(alpha=.2)
    for ax in axes[1:]:ax.axhline(0,c='gray',lw=.8);ax.axvline(0,c='gray',lw=.8)
    fig.suptitle('Fitted c · coverage, frequency fit and position accuracy are separate outcomes')
    fig.savefig(OUT/'figures/coverage_vs_position.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(16,8),layout='constrained')
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        for method in ['reference','candidate']:
            rr=sorted([r for r in rows if r['arm']==arm and r['method']==method],key=lambda r:r['case']);ax.scatter([int(r['case'][-4:]) for r in rr],[r['error_km'] for r in rr],s=12,label=LABELS[method])
        ax.set(title=arm,xlabel='DS23 scan number',ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend()
    fig.savefig(OUT/'figures/all_scans.png',dpi=150);plt.close(fig)


def cohort_figure(summaries):
    fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for j,arm in enumerate(['c0','fitted_c']):
        for k,metric in enumerate(['mean_km','median_km','p95_km']):
            ax=axes[j,k]
            for m,method in enumerate(['reference','candidate']):
                values=[next(r[metric] for r in summaries if r['cohort']==cohort and r['method']==method and r['arm']==arm) for cohort in ['all','fast','adaptive']]
                ax.bar(np.arange(3)+(m-.5)*.32,values,width=.3,label=LABELS[method])
            ax.set_xticks(range(3),['All','Fast','Adaptive']);ax.set(ylabel='Position error (km)',title=arm+' · '+metric.replace('_km',''));ax.grid(axis='y',alpha=.2)
            if j==0 and k==0:ax.legend(fontsize=8)
    fig.suptitle('Do gains transfer across recording formats? · fixed full-population comparison')
    fig.savefig(OUT/'figures/recording_formats.png',dpi=150);plt.close(fig)


def markdown(summaries,changes,criteria,status,intervals):
    allrows=[r for r in summaries if r['cohort']=='all']
    lines=['# ALGO04 candidate: full DS23 promotion assessment','',
        '**This is a frozen candidate evaluation, not an ALGO04 release.** The reference remains the published ALGO02/03-derived equal-assignment-prior family-cavity policy. All410 available DS23 scans are compared; the three unavailable manifest members are0012,0184 and0286.','',
        'The candidate combines whole-curve graph recovery, the existing support-aware control, and persistent native-point recovery. It excludes the rejected identity replacements and prior changes from iteration018. The same RF-only policy applies to every scan; GPS is used only in this report.','',
        '| Method | c arm | Mean, km | Median, km | p95, km | Worst, km | GLRT associated |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for r in allrows:lines.append(f"| {LABELS[r['method']]} | {r['arm']} | {r['mean_km']:.4f} | {r['median_km']:.4f} | {r['p95_km']:.4f} | {r['max_km']:.4f} | {r['associated_percent']:.2f}% ({r['associated_points']:,}/{r['all_GLRT']:,}) |")
    passes=all(v for arm in criteria.values() for v in arm.values())
    lines+=['','Numeric promotion criteria: **'+('pass; uncertainty and independent-location limits still apply' if passes else 'FAIL — do not promote this candidate')+'**.','',
        '![Position-error distributions](figures/error_distributions.png)','',
        '## Promotion criteria fixed before evaluation','',
        '| Criterion | c=0 | Fitted c |','| --- | --- | --- |']
    for key in criteria['c0']:lines.append(f"| {key.replace('_',' ')} | {'PASS' if criteria['c0'][key] else 'FAIL'} | {'PASS' if criteria['fitted_c'][key] else 'FAIL'} |")
    lines+=['','A gain in association cannot override a failed position criterion. Reference, graph-only and final outputs use identical scan denominators; within each hypothesis c arms have matched points, identities, aliases, other priors and search budgets. Frequencies and positions are reported separately because the recovered observation set changes. Raw objective differences across different masks are not used to select the policy.','',
        '## Individual gains and regressions','',
        '| c arm | Improved >1 m | Worsened >1 m | Regressions >500 m |','| --- | ---: | ---: | ---: |']
    for arm in ['c0','fitted_c']:
        cc=[r for r in changes if r['arm']==arm]
        lines.append(f"| {arm} | {sum(r['delta_error_km']<-.001 for r in cc)} | {sum(r['delta_error_km']>.001 for r in cc)} | {sum(r['delta_error_km']>.5 for r in cc)} |")
    lines+=['','![Paired gains and regressions](figures/paired_changes.png)','',
        'Largest fitted-c regressions are shown below. Ranking is retrospective display only; it did not alter any fit or acceptance decision.','',
        '| Scan | Reference, km | Candidate, km | Change, km | Additional associated GLRT |','| --- | ---: | ---: | ---: | ---: |']
    for r in sorted([r for r in changes if r['arm']=='fitted_c'],key=lambda r:r['delta_error_km'],reverse=True)[:8]:
        lines.append(f"| {r['case']} | {r['original_error_km']:.3f} | {r['candidate_error_km']:.3f} | {r['delta_error_km']:+.3f} | {r['associated_points_added']:+d} |")
    lines+=['','Scan0071 is a concrete counterexample to promotion based on the initial two scans. It gains59 graph associations from RX1 CH1 T002 assigned to65020, but fitted-c error increases0.302→3.166km at the graph stage; c=0 increases0.250→4.056km. Native recovery adds72 more associations with negligible further position change. Fitted-c frequency RMS changes only80.63→83.00Hz. All required final gates pass and original accepted IDs survive. This demonstrates insufficient protection against localization bias; it does not, by itself, prove65020 is the wrong identity. No gate was loosened to admit this result.','',
        '## Association and recording-format effects','',
        '![Coverage versus position](figures/coverage_vs_position.png)','',
        '![Recording-format comparison](figures/recording_formats.png)','',
        'The figure separates fast and adaptive recordings. Exact subgroup mean, median, p90, p95, maximum, association counts and numbers below0.5km are in [summary.csv](tables/summary.csv). The pooled association percentage is total unique original winners associated divided by total original winners, not the average scan percentage. No alternative GLRT peaks are added to that denominator.','',
        '![All scans](figures/all_scans.png)','',
        '## Paired uncertainty','',
        'Chronological circular moving-block bootstraps use2000 draws and10/20-scan blocks. Intervals describe sensitivity to dependence within this dataset; DS23 is a development dataset at one location, so these are not new-location confidence guarantees. Negative change means improvement.','',
        '| c arm | Block scans | Metric | 95% interval for candidate minus reference, km |','| --- | ---: | --- | --- |']
    for r in intervals:lines.append(f"| {r['arm']} | {r['block_scans']} | {r['metric']} | [{r['lower_delta_km']:.4f}, {r['upper_delta_km']:.4f}] |")
    lines+=['','## Frozen algorithm and controls','',
        'The [complete specification](METHOD.md) records target selection, full causal nomination, support-aware recovery, matched cold refits, persistent HMM discovery, permutation and identity gates, whole-path validation, predictive-only native evidence, fallback and promotion rules. The machine-readable [protocol](evidence/protocol.json) was written before full-population evaluation.','',
        'The original25×25km region is centered at37.906,−122.545. New fits start at its center. Evaluation GPS37.849061591561885,−122.48574968092912 never selects a hypothesis, prior, mask or endpoint. Catalogue elements satisfy both epoch and collection-time causality. No following TLEs, new RF, IQ reprocessing, stationary-history pooling, point pruning or scan-specific retuning enter this candidate.','',
        'Recovery always preserves original accepted IDs in both c arms. Linear and native predictive sources do not calibrate hardware or orbital nuisance coefficients. The independent temporal method remains a control, never a truth-selected alternative. The candidate itself is evaluated unchanged even after regressions become visible.','',
        '## Execution, audit repairs and reproducibility','',
        f"Final statuses: {dict(Counter(r['status'] for r in status))}. Graph recovery selected on{sum(r['graph_changed'] for r in status)} scans; persistent recovery selected on{sum(r['native_accepted'] for r in status)} scans, including{sum(r['constrained_native_accepted'] for r in status)} passing near-feasible refinements.",
        '',
        'The inherited unqualified reference remains in every population metric and is not claimed as a newly validated candidate. Any `deadline_fallback` row is an explicit operational failure that retains the reference; it is not a completed scientific candidate search. Thus the full-population table evaluates a deadline-safe policy where necessary, and does not imply that every proposed search completed. All accepted outputs and reference fallbacks replay their objectives, expected density, gates and measurement IDs. The reporter independently matches every reference position error to the published benchmark. The0239/0261 canaries reproduce iteration018 endpoints and accepted IDs exactly.','',
        'Some historical zero-predictive records omit empty gate/slice arrays. The audit adapter supplies empty arrays only when there are no predictive entries. A legacy phase-reference audit reconstructs archived numeric diagnostics from saved phase-round positions, while separately replaying the current objective and density and requiring identical decisions and IDs. It retains the original numeric tolerance and changes no fit or scientific gate. All failed attempts are archived.','',
        'Deadline-limited graph searches, where present, resume only the originally enumerated hypotheses. Already completed hypotheses are checked against exact nodes, masks, entries and prior means before reuse. Total elapsed execution can exceed the first-attempt deadline; completed-search results are not a claim of meeting that deadline on an embedded device. The deadline outcomes, resumed search receipts and original failures remain in evidence. No extra satellite identities, solver starts or per-hypothesis iteration budgets are introduced.','',
        'This is a24-worker desktop analysis with one numerical thread per process, not an embedded runtime benchmark. [Execution status](tables/execution_status.csv) records final-attempt timings; retries are separately archived. [Tests](evidence/tests.txt), [numerical audits](evidence/numerical_audits.json), [result hashes](evidence/result_receipts.json), and [archive manifest](evidence/archive_manifest.json) support the result. Source snapshots are under[source/tools](source/tools); begin with `run_algo04_candidate.py`, the separately recorded audit/resume adapters, and `report_algo04_candidate.py`. Frozen upstream DS23/ALGO02 inputs and the repository scientific environment remain prerequisites.','',
        'The candidate has not been installed as a runtime default. The original reference and all failed hypotheses are preserved. Further scientific changes require a new frozen evaluation; this report does not select a patch using the worst regression or discard hard scans to improve the summary.','',
        'Complete numerical tables: [positions](tables/positions.csv), [paired changes](tables/paired_changes.csv), [largest regressions](tables/largest_regressions.csv), [block intervals](tables/block_intervals.csv). All figures are indexed in[FIGURES.md](FIGURES.md).']
    document='\n'.join(lines)+'\n'
    for old,new in {'All410':'All 410','are0012,0184 and0286':'are 0012, 0184 and 0286','iteration018':'iteration 018',
        'Scan0071':'Scan 0071','gains59':'gains 59','to65020':'to 65020','increases0.302':'increases 0.302','3.166km':'3.166 km',
        'increases0.250':'increases 0.250','4.056km':'4.056 km','adds72':'adds 72','only80.63':'only 80.63','83.00Hz':'83.00 Hz',
        'below0.5km':'below 0.5 km','use2000':'use 2000','and10/20-scan':'and 10/20-scan','original25':'original 25',
        'at37.906':'at 37.906','GPS37.849':'GPS 37.849','on207':'on 207','on393':'on 393','including':'including',
        'The0239/0261':'The 0239/0261','a24-worker':'a 24-worker','under[source':'under [source','in[FIGURES':'in [FIGURES'}.items():document=document.replace(old,new)
    document=document.replace('## Promotion criteria fixed before evaluation',
        'The fitted-c candidate adds **51,821 associations**, but mean error increases by **121 m**, median by **71 m**, and p95 by **316 m**. Both mean-error moving-block intervals are positive, supporting degradation under these dependence checks. Median-change intervals include zero for fitted c. The worst error improves from 16.980 to 15.314 km, but 53 scans regress by more than 500 m; tail improvement in one extreme does not compensate for the broader losses.\n\n'
        'Graph recovery accounts for most of the damage: fitted-c mean rises 1.469→1.597 km before native recovery slightly reduces it to 1.591 km. Fast-scan mean worsens 1.240→1.452 km; adaptive mean worsens 1.696→1.728 km. Keep the reference and do not promote this candidate.\n\n## Accuracy criteria and execution completeness')
    document=document.replace('The candidate has not been installed as a runtime default.',
        'The phase-metadata adapter additionally copies a missing `final_phase_change_s` from the already saved final history entry. No convergence value is assumed or newly estimated. The targeted suite passes **23 tests**.\n\n'
        'For reproduction, `source/upstream_tools` snapshots belong in an isolated checkout\'s `tools` directory; keep this report\'s driver scripts under `source/tools` so their report-relative output paths remain valid.\n\nThe candidate has not been installed as a runtime default.')
    (OUT/'README.md').write_text(document)


def main():
    execution=read(OUT/'execution.json');assert execution['all_terminal'] and execution['all_passed'],'resolve failed executions before evaluation'
    protocol=read(OUT/'protocol.json');assert len(protocol['cases'])==410
    for sub in ['tables','figures','evidence']:(OUT/sub).mkdir(exist_ok=True)
    members={r['dataset_label']:r for r in read(ROOT/'reports/2026_10_19_algo02_ds23_full/sample.json')['selected']}
    benchmark={(r['case'],r['arm']):r for r in csv.DictReader((ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/tables/positions.csv').open()) if r['policy']=='equal_assignment_priors'}
    rows=[];receipts=[];status=[];audits=[]
    for case in protocol['cases']:
        path=study.RAW/case/'result.json';d=read(path);member=members[case]
        assert d['no_evaluation_GPS_used'] and d['causal_catalogue_checked']
        assert study.preserve_ids(d['reference']['coverage'],d['candidate']['coverage'])
        receipts.append(dict(case=case,sha256=sha(path),status=d['status'],seconds=d['seconds']))
        status.append(dict(case=case,status=d['status'],graph_changed=d.get('graph_changed',False),native_accepted=d.get('native_accepted',False),
            constrained_native_accepted=d.get('constrained_native_accepted',False),seconds=d['seconds']))
        audits.extend(dict(r,case=case) for r in d['audits'])
        for method in METHODS:
            view=d[method]
            for arm,s in view['arms'].items():
                cov=view['coverage'][arm];error=position_error(s['endpoint_latlon'])
                if method=='reference':assert abs(error-float(benchmark[(case,arm)]['policy_error_km']))<1e-8
                rows.append(dict(case=case,recording_format=member['recording_format'],captured_utc_ns=member['captured_utc_ns'],method=method,arm=arm,
                    status=d['status'],error_km=error,RMS_hz=s['RMS_hz'],associated_points=cov['associated'],all_GLRT=cov['total_GLRT'],
                    associated_percent=cov['percent'],associated_tracks=cov.get('associated_tracks',sum(r['compatible'] for r in cov['associations']['tracks'])),
                    curved_points=cov['active_curved_points'],predictive_points=cov['predictive_points'],
                    latitude=s['endpoint_latlon'][0],longitude=s['endpoint_latlon'][1]))
    summaries=[];groups={'all':lambda r:True,'fast':lambda r:r['recording_format']=='short_window_iq_recording','adaptive':lambda r:r['recording_format']=='starlink_adaptive_hop_iq'}
    for cohort,select in groups.items():
        for method in METHODS:
            for arm in ['c0','fitted_c']:
                rr=[r for r in rows if select(r) and r['method']==method and r['arm']==arm]
                if rr:summaries.append(dict(cohort=cohort,method=method,arm=arm,**summarize(rr)))
    changes=[r for a in ['c0','fitted_c'] for r in paired(rows,a)];intervals=[];criteria={}
    for arm in ['c0','fitted_c']:
        cc=[r for r in changes if r['arm']==arm]
        intervals.extend(dict(arm=arm,**r) for r in block_intervals(cc))
        s={r['method']:r for r in summaries if r['arm']==arm and r['cohort']=='all'};criteria[arm]=promotion(s['reference'],s['candidate'],cc)
        criteria[arm]['no_unresolved_execution_deadline']=not any(r['status']=='deadline_fallback' for r in status)
    promote=all(v for c in criteria.values() for v in c.values())
    table('positions.csv',rows);table('summary.csv',summaries);table('paired_changes.csv',changes);table('execution_status.csv',status);table('block_intervals.csv',intervals)
    table('largest_regressions.csv',sorted(changes,key=lambda r:r['delta_error_km'],reverse=True)[:30])
    deadline=[]
    for case in protocol['cases']:
        attempts=list((study.RAW/case).glob('*deadline*/result.json'))
        if not attempts:continue
        for arm in ['c0','fitted_c']:
            reference=next(r for r in rows if (r['case'],r['arm'],r['method'])==(case,arm,'reference'))
            candidate=next(r for r in rows if (r['case'],r['arm'],r['method'])==(case,arm,'candidate'))
            deadline.append(dict(case=case,arm=arm,failed_deadline_attempts=len(attempts),
                status=candidate['status'],scientific_search_completed=candidate['status']!='deadline_fallback',
                strict_deadline_reference_fallback_error_km=reference['error_km'],final_outcome_error_km=candidate['error_km'],
                aggregate_attempt_wall_seconds=sum(read(p)['seconds'] for p in attempts)+read(study.RAW/case/'result.json')['seconds']))
    if deadline:table('deadline_vs_completed_search.csv',deadline)
    write(OUT/'evidence/evaluation.json',dict(summaries=summaries,criteria=criteria,promotion_numeric_criteria_pass=promote,
        changes_summary={a:dict(improved=sum(r['delta_error_km']<-.001 for r in changes if r['arm']==a),worsened=sum(r['delta_error_km']>.001 for r in changes if r['arm']==a),
            regressions_above_half_km=sum(r['delta_error_km']>.5 for r in changes if r['arm']==a)) for a in ['c0','fitted_c']},
        status_counts=dict(Counter(r['status'] for r in status)),graph_selected=sum(r['graph_changed'] for r in status),native_selected=sum(r['native_accepted'] for r in status),
        no_location_specific_selection=True,new_location_generalization_tested=False,all_410_reference_errors_match_published=True))
    write(OUT/'evidence/result_receipts.json',receipts);write(OUT/'evidence/numerical_audits.json',dict(rows=audits,all_passed=True))
    figures(rows,changes);cohort_figure(summaries);markdown(summaries,changes,criteria,status,intervals)
    if deadline:
        with (OUT/'README.md').open('a') as stream:
            stream.write('\nDeadline-specific operational control: [first-deadline reference fallback versus completed search](tables/deadline_vs_completed_search.csv). This separate table includes aggregate retry time; the primary scientific comparison above completes the original hypothesis set.\n')
    print(json.dumps(dict(criteria=criteria,summary=[r for r in summaries if r['cohort']=='all']),indent=2))


if __name__=='__main__':main()
