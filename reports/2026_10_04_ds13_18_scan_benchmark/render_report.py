"""Render the evidence-backed campaign report, explicitly marking unfinished work."""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from cohort import OUT, digest


def finalist_section(output,sources):
    protocol_path=output/'validation-shortlist.json'
    if not protocol_path.exists():return ''
    protocol=json.loads(protocol_path.read_text())
    for path,expected in protocol['sources'].items():
        if digest(Path(path).read_bytes())!=expected:raise ValueError('validation development evidence changed')
    sources[str(protocol_path)]=digest(protocol_path.read_bytes())
    content='''<section class="card"><h2>Frozen validation shortlist</h2>
<p>Four configurations: the 600 Hz baseline, a 300 Hz gate, a 900 Hz gate, and the 1.1 curvature filter. Satellite penalty remains 10; timing-prior widths remain at baseline. All configurations retain matched fitted-c and c=0 position comparisons. The four test scans remain locked until final settings are recorded.</p>
<p>The predeclared selection rule requires at least three common, converged, interior validation results. A challenger must reduce median position error by at least 20% without more failures. Otherwise the baseline remains the reference; insufficient evidence is reported as inconclusive, not an optimum. Raw likelihoods from different observation subsets are not comparable model-selection scores.</p>
<p><a href="validation-shortlist.json">Frozen shortlist and development evidence</a></p>'''
    path=output/'finalist-comparison/summary.json'
    if path.exists():
        summary=json.loads(path.read_text())
        for source,expected in summary['sources'].items():
            if digest(Path(source).read_bytes())!=expected:raise ValueError('finalist position evidence changed')
        sources[str(path)]=digest(path.read_bytes())
        validation=[r for r in summary['rows'] if r['split']=='validation' and r['arm']=='fitted-c']
        content+=f'<p>Completed validation configuration/scan pairs: {len(validation)}/16. Eligibility includes numerical convergence and excludes boundary or calibration-warning results. Missing results are not zero error.</p>'
        if (output/'finalist-comparison/position-comparison.png').exists():
            content+='<img src="finalist-comparison/position-comparison.png" alt="Development pilots and validation position comparisons with numerical failure flags">'
        content+='<p><a href="finalist-comparison/summary.csv">Position, coverage, and common-300-Hz support table</a></p>'
    final=output/'final-settings.json'
    if final.exists():
        from freeze_final_settings import read_freeze
        frozen=read_freeze(output);decision=frozen['decision']
        sources[str(final)]=digest(final.read_bytes())
        content=content.replace('The four test scans remain locked until final settings are recorded.',
                                'Final settings have now been frozen; test scans are evaluated without further tuning.')
        comparison_rows=[]
        for row in decision['comparisons']:
            reduction=row['relative_median_reduction']
            values=(row['configuration'],', '.join(row['common_eligible_scans']) or 'None',row['failures'],
                    f'{100*reduction:+.1f}%' if reduction is not None else 'Not estimable',row['qualifies'])
            comparison_rows.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in values)+'</tr>')
        content+=f'''<h3>Frozen decision: {html.escape(decision['selected_configuration'])}</h3>
<p>Status: <code>{html.escape(decision['status'])}</code>. This is a conservative reference choice, not proof of optimal settings. The baseline has {decision['baseline_failures']} ineligible validation result(s) out of four.</p>
<table><thead><tr><th>Challenger</th><th>Common eligible scans</th><th>Ineligible / 4</th><th>Median error reduction</th><th>Qualifies</th></tr></thead><tbody>{''.join(comparison_rows)}</tbody></table>
<p><a href="final-settings.json">Frozen settings, selection decision and source hashes</a></p>'''
    return content+'</section>'


def heldout_section(output,sources):
    path=output/'heldout-calibration/summary.json'
    if not path.exists():return ''
    document=json.loads(path.read_text())
    for source,expected in document['sources'].items():
        if digest(Path(source).read_bytes())!=expected:raise ValueError('held-out calibration evidence changed')
    sources[str(path)]=digest(path.read_bytes())
    return '''<section class="card"><h2>Conditional held-out calibration transfer</h2>
<p>Five blocked folds per scan compare fitted-c with c=0 using the same training/test rows, bootstrap satellite bank, receiver spline and fit budgets. Whole-scan shapes supplied the bootstrap bank and initialization: this measures nuisance transfer, not fully held-out satellite identification.</p>
<p>The RMS conditions on each arm's own points within 600 Hz of its nearest visible bootstrap orbit. Its denominator can differ between arms; read it together with coverage and convergence. These figures are separate from final exhaustive association coverage and do not establish localization accuracy.</p>
<img src="heldout-calibration/comparison.png" alt="Held-out coverage, gated RMS and convergence for both RF arms">
<p><a href="heldout-calibration/summary.csv">All scan-level calibration transfer metrics</a></p></section>'''


def position_completion(rows):
    expected={(ranking,fraction,arm) for ranking in ('rms','support','glrt')
              for fraction in (.25,.5,.75) for arm in ('fitted-c','zero-c')}
    expected|={('support',1.,arm) for arm in ('fitted-c','zero-c')}
    labels={r['scan'] for r in rows}
    full=sum(all(any(r['scan']==label and r['fraction']==1. and r['arm']==arm for r in rows)
                 for arm in ('fitted-c','zero-c')) for label in labels)
    subsets=sum(expected<={(r['ranking'],r['fraction'],r['arm']) for r in rows if r['scan']==label} for label in labels)
    return full,subsets


def leaderboard_section(output,sources):
    path=output/'leaderboard/summary.json'
    if not path.exists():return ''
    document=json.loads(path.read_text())
    for source,expected in document['sources'].items():
        if digest(Path(source).read_bytes())!=expected:raise ValueError('cohort leaderboard evidence changed')
    sources[str(path)]=digest(path.read_bytes())
    table=[]
    for row in document['aggregate']:
        median=row['paired_eligible_median_error_m'];tail=row['paired_eligible_p90_error_m']
        values=(row['split'],row['arm'],row['association_scans'],f"{100*row['equal_scan_mean_coverage']:.1f}%",
                f"{row['scans_at_least_90_percent']}/{row['association_scans']}",
                f"{row['equal_scan_mean_satellites']:.1f}",f"{row['position_ineligible']}/{row['position_scans']}",
                ', '.join(row['common_eligible_scans']) or 'None',
                f'{median:.0f}' if median is not None else 'Not estimable',f'{tail:.0f}' if tail is not None else 'Not estimable')
        table.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in values)+'</tr>')
    interpretation=heldout_interpretation(document.get('rows',[]))
    return '''<section class="card"><h2>Frozen-baseline cohort summary</h2>
<p>Each scan has an independent position estimate. Coverage averages give every scan equal weight. Position summaries below use only scans eligible in <em>both</em> RF arms, so neither arm benefits from dropping its own difficult cases. Small eligible sample counts limit generalization; the table lists them explicitly. These are best-found conditional locations, not certified global minima.</p>
<img src="leaderboard/overview.png" alt="Per-scan association coverage, residual fit, position distance and computation time with failed positions flagged">
<div style="overflow-x:auto"><table><thead><tr><th>Split</th><th>RF</th><th>Association scans</th><th>Mean coverage</th><th>Scans ≥90%</th><th>Mean satellites</th><th>Ineligible positions</th><th>Common eligible scans</th><th>Paired median (m)</th><th>Paired P90 (m)</th></tr></thead><tbody>'''+''.join(table)+'''</tbody></table></div>
<p>The 90% threshold is evaluated before display rounding: 89.97% is below 90%, even if a one-decimal chart label rounds to 90.0%.</p>'''+interpretation+'''
<p><a href="leaderboard/per-scan.csv">Every scan × association method × RF arm</a> · <a href="leaderboard/by-split.csv">Split-level aggregate CSV</a>. Positions use the alternatives method. Per-method residual RMS uses each method's own assigned samples; it must not be substituted for matched-observation position accuracy. Saved fit times exclude refinement and orbit discovery and do not equal total campaign time.</p>
<h3>What each association step changes</h3>
<img src="leaderboard/method-gains.png" alt="Changes in assigned windows, satellite counts and penalized score from replacement and alternative candidates">
<p>The objective rewards explained windows but charges 10 per satellite. Coverage need not increase when the score improves: in N08, the fitted-c alternatives result gives up 11 windows while removing two satellites, a net score gain of 9. A zero bar for replacement means no score improvement was found within the bounded replacement search, not proof that greedy is globally optimal. Alternative-candidate compatibility is not independent confirmation of identity.</p>
<p><a href="leaderboard/method-gains.csv">Exact per-scan changes for both RF arms</a></p></section>'''


def heldout_interpretation(rows):
    """Explain complete test association evidence without claiming position success."""
    selected=[r for r in rows if r['split']=='locked_test' and
              r['method']=='alternatives' and r['arm']=='fitted-c']
    if len(selected)!=4 or len({r['scan'] for r in selected})!=4:
        return '<p>Held-out association interpretation is pending all four test scans.</p>'
    coverage=[r['coverage'] for r in selected]
    above=sum(x>=.9 for x in coverage)
    positions=sum(r.get('position_error_m') is not None for r in selected)
    eligible_positions=sum(r.get('position_error_m') is not None and r.get('position_eligible') is True for r in selected)
    details=[]
    for row in rows:
        if row['split']!='locked_test' or row['method']!='alternatives' or row.get('position_error_m') is None:continue
        kkt=row.get('best_kkt_residual')
        values=(row['scan'],row['arm'],f"{row['position_error_m']:.0f}",row.get('best_fit_status','Not recorded'),
                f'{kkt:.4g}' if kkt is not None else 'Not recorded',row.get('boundary'),row.get('position_eligible'))
        details.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in values)+'</tr>')
    table=('''<table><thead><tr><th>Test scan</th><th>RF</th><th>Saved distance (m)</th><th>Termination</th><th>Stationarity residual</th><th>Boundary</th><th>Eligible</th></tr></thead><tbody>'''+''.join(details)+'''</tbody></table>
<p>The stationarity residual accounts for active constraints in scaled parameter coordinates; the numerical acceptance threshold is 0.001. A time limit or a missing descent step does not establish that the association model itself is wrong. Equal maximum wall-time budgets do not guarantee equal iteration counts on a shared machine.</p>''') if details else ''
    return f'''<h3>What the held-out association results establish</h3>
<p>The frozen alternatives model explains {100*min(coverage):.2f}%–{100*max(coverage):.2f}% of passing windows across the four test scans; {above}/4 reach 90% before rounding. This is conditional orbit compatibility at the known roof, not confirmed satellite identity. These results do not establish a general 90% recovery guarantee.</p>
<p>Full-membership position results are present for {positions}/4 test scans. Of these completed fitted-c results, {eligible_positions}/{positions} pass the convergence, interior-location and calibration checks. Ineligible results cannot establish position accuracy, even when their saved coordinates happen to lie near the roof. Higher coverage alone is not evidence of a less biased position.</p>
{table}
<p>Keep the frozen test outcomes unchanged: any future timing, calibration or catalogue changes should be developed on the development scans and evaluated on a new holdout, not selected to repair these four results. If convergence failures prevent comparison, diagnose numerical convergence before attributing all position error to bad satellite associations or choosing stronger priors.</p>'''


def validate_export(document, scan, cohort_hash):
    if document['signature']['cohort_sha256'] != cohort_hash:
        raise ValueError('export does not bind current cohort')
    if document['signature']['manifest_sha256'] != scan['manifest_sha256']:
        raise ValueError('capture digest mismatch')
    rows = document['records']
    summary = document['summary']
    if len(rows) != summary['projected_passing_candidates']:
        raise ValueError('candidate accounting mismatch')
    if len({r['candidate_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate candidate IDs')
    if len({r['group_id'] for r in rows}) != summary['passing_windows']:
        raise ValueError('window accounting mismatch')


def require_final_audit(result):
    if result.get('status')!='analysis_artifacts_verified' or not result.get('checks') or not all(c['verified'] for c in result['checks']):
        raise ValueError('cannot publish a complete report while required evidence is missing or invalid')


def render(inputs, output, final=False):
    if final:
        from audit_campaign import audit
        require_final_audit(audit(inputs,output))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    cohort_path = OUT/'cohort-v2.json'
    raw = cohort_path.read_bytes()
    cohort = json.loads(raw)
    rows, sources = [], {str(cohort_path): digest(raw), str(Path(__file__)): digest(Path(__file__).read_bytes())}
    for scan in cohort['scans']:
        row = dict(scan)
        path = inputs/scan['label']/'observations.json'
        if path.exists():
            document = json.loads(path.read_text())
            validate_export(document, scan, digest(raw))
            row['export'] = document['summary']
            sources[str(path)] = digest(path.read_bytes())
        progress = inputs/scan['label']/'refinement/progress.json'
        if progress.exists():
            result = json.loads(progress.read_text())
            if result['signature']['observations_sha256'] != sources.get(str(path)):
                raise ValueError('refinement references different observations')
            row['refinement'] = result
            sources[str(progress)] = digest(progress.read_bytes())
        rows.append(row)
    output.mkdir(parents=True, exist_ok=True)
    colors = dict(reference='#676b73', development='#0072b2', validation='#e69f00', locked_test='#009e73')
    fig, axes = plt.subplots(1, 2, figsize=(15, 8), gridspec_kw={'width_ratios': [1.4, 1]})
    ordered = sorted(rows, key=lambda r:r['capture_start_ns'])
    origin = min(r['capture_start_ns'] for r in ordered)
    for i, row in enumerate(ordered):
        x = (row['capture_start_ns']-origin)/3.6e12
        axes[0].scatter(x, i, color=colors[row['split']], s=70, zorder=3)
        axes[0].text(x+.4, i, row['capture_local'][5:16].replace('T', ' '), fontsize=8, va='center')
    axes[0].set(yticks=range(18), yticklabels=[r['label'] for r in ordered], xlabel='Hours since earliest selected capture', title='Frozen cohort · time-separated selection')
    axes[0].invert_yaxis()
    axes[0].set_xlim(-1, (max(r['capture_start_ns'] for r in ordered)-origin)/3.6e12+12)
    for split, color in colors.items():
        axes[0].scatter([], [], color=color, label=split.replace('_', ' '))
    axes[0].legend(loc='lower left', fontsize=8)
    available = [r for r in rows if 'export' in r]
    xx = np.arange(len(available))
    axes[1].barh(xx, [r['export']['all_scheduled_probes'] for r in available], color='#e3e6eb', label='Scheduled probes')
    axes[1].barh(xx, [r['export']['passing_windows'] for r in available], color=[colors[r['split']] for r in available], label='Windows with passing GLRT')
    axes[1].set(yticks=xx, yticklabels=[r['label'] for r in available], xlabel='Unique receiver/channel/20 ms windows', title='Input activity · not satellite-association coverage')
    axes[1].invert_yaxis()
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis='x', alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle('18-scan offline benchmark · cohort and frozen input denominators', fontsize=16)
    fig.text(.5, .014, 'All additions and B: 2.5 MS/s. Historical A: 10 MS/s. Times printed in America/Los_Angeles.\n40° is the included mount-axis separation, not beam width. No new RF capture.', ha='center', fontsize=9)
    fig.tight_layout(rect=(0,.065,1,.95))
    fig.savefig(output/'cohort-and-inputs.png', dpi=145)
    plt.close(fig)
    table = []
    for row in rows:
        ex, rr = row.get('export', {}), row.get('refinement', {})
        status = (f"{rr['completed_candidates']:,}/{rr['total_candidates']:,} ({rr['status']})" if rr else 'Pending')
        table.append('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in (
            row['label'], row['session_id'], row['split'], row['capture_local'],
            row['sample_rate_hz']/1e6, ex.get('projected_passing_candidates', 'Pending'),
            ex.get('passing_windows', 'Pending'), status)) + '</tr>')
    completed = sum(r.get('refinement', {}).get('status') == 'complete' for r in rows)
    pilot_sections = []
    overview=[]
    for scan in cohort['scans']:
        label = scan['label']
        metrics = output/f'pilot-{label}/pilot-metrics.json'
        seeded = output/f'pilot-{label}-seeded/pilot-metrics.json'
        if seeded.exists():
            metrics = seeded
        if not metrics.exists():
            continue
        pilot = json.loads(metrics.read_text())
        if pilot['session_id'] != scan['session_id']:
            raise ValueError('pilot scan binding mismatch')
        for path, expected in pilot['sources'].items():
            if digest(Path(path).read_bytes()) != expected:
                raise ValueError('pilot metrics are stale')
        sources[str(metrics)] = digest(metrics.read_bytes())
        folder=metrics.parent.name
        variant=pilot.get('variant','initial-bootstrap')
        warnings=pilot.get('calibration_warnings',[])
        warning_text=(f'<p class="warning"><strong>Calibration warning:</strong> {len(warnings)} folds have nonconverged fitted models. Coverage is diagnostic, not a validated optimum.</p>' if warnings else '')
        variant_text=('Corrected receiver-line initialization retains individual satellite timing seeds.' if variant.startswith('seed-timing-')
                      else 'Legacy initialization baseline: individual timing seeds were omitted during RX-line initialization. A corrected, separately saved initialization is being tested; do not treat these as final cohort results.')
        diagnostics=''
        position_sections=[]
        for position_path in sorted(metrics.parent.glob('position-*.json')):
            evidence=json.loads(position_path.read_text())
            if digest(Path(evidence['source']).read_bytes())!=evidence['source_sha256']:
                raise ValueError('stale position figure input')
            sources[str(position_path)]=digest(position_path.read_bytes())
            position_sections.append(f'<img src="{folder}/{position_path.stem}.png" alt="Independent position search with convergence flags">')
        if (metrics.parent/'alternatives-track-statistics.csv').exists():
            diagnostics=f'''<p><a href="{folder}/alternatives-track-statistics.csv">Per-track statistics CSV</a> ·
<a href="{folder}/alternatives-fitted-c-residuals.png">Fitted-c residual panels</a> ·
<a href="{folder}/alternatives-zero-c-residuals.png">c=0 residual panels</a></p>
<details><summary>Nominal antenna orientation diagnostic</summary><img src="{folder}/alternatives-orientation.png" alt="Nominal pointing angle versus east/west hemisphere mismatch"></details>'''
        gradient_path=metrics.parent/'satellite-gradients.json'
        if gradient_path.exists():
            gradient_evidence=json.loads(gradient_path.read_text())
            # Never mix an older initialization's gradient with newly rendered
            # association results sharing the same display directory.
            if all(variant in [p.name for p in Path(path).parents] for path in gradient_evidence['sources']):
                for path,expected in gradient_evidence['sources'].items():
                    if digest(Path(path).read_bytes())!=expected:
                        raise ValueError('stale satellite-gradient input')
                sources[str(gradient_path)]=digest(gradient_path.read_bytes())
                diagnostics+=f'''<details><summary>Satellite/RX gradient contributions</summary>
<img src="{folder}/satellite-gradients.png" alt="Additive satellite contributions to roof score derivative">
<p><a href="{folder}/satellite-gradients.csv">All gradient components (CSV)</a>. These add to the soft-likelihood gradient, not hard-assignment residual sums. A nonconverged roof fit does not establish the profiled position gradient.</p></details>'''
        result_rows = []
        links = []
        for result in pilot['comparisons']:
            overview.append(dict(scan=label,split=scan['split'],variant=variant,**result))
            result_rows.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in (
                result['arm'],result['method'],result['assigned'],result['unassigned'],
                f"{100*result['coverage']:.1f}%",result['satellites'],result['objective']))+'</tr>')
            name = f"{result['method']}-{result['arm']}-orbits.png"
            links.append(f'<a href="{folder}/{name}">{result["method"]} · {result["arm"]}</a>')
        pilot_sections.append(f'''<section class="card"><h2>Scan {label}: association comparison</h2>
<p><strong>{variant}</strong> · {variant_text}</p>{warning_text}
<p>{html.escape(scan['session_id'])} · {html.escape(scan['split'])}. This is a conditional known-roof search, not blind localization or confirmed satellite identity. Cross-fitted receiver calibration is frozen; satellite identities and timing modes use the full scan. The same satellite/timing hypothesis pool and original window denominator are used in both RF arms.</p>
<img src="{folder}/association-comparison.png" alt="Pilot method and RF ablation comparison">
<table><thead><tr><th>RF arm</th><th>Method</th><th>Associated</th><th>Unassociated</th><th>Coverage</th><th>Satellites</th><th>Penalized score</th></tr></thead><tbody>{''.join(result_rows)}</tbody></table>
<p>Orbit + all windows and unassociated-only figures: {' · '.join(links)}.</p>
<img src="{folder}/refinement-comparison.png" alt="Pilot refinement and candidate/window accounting">
<details><summary>Show alternatives / fitted-c orbit plot</summary><img src="{folder}/alternatives-fitted-c-orbits.png" alt="All windows and associated orbits beside unassociated windows"></details>
{diagnostics}
{''.join(position_sections)}
<p>These coverage results alone cannot establish a localization improvement. The position/subset and held-out comparisons are reported separately, with unfinished cases explicitly marked.</p></section>''')
    screening=''
    position_overview=''
    complete_positions,complete_subsets=0,0
    position_summary=output/'position-summary/position-summary.json'
    if position_summary.exists():
        summary=json.loads(position_summary.read_text())
        complete_positions,complete_subsets=position_completion(summary['rows'])
        for source,expected in summary['sources'].items():
            if digest(Path(source).read_bytes())!=expected:raise ValueError('stale aggregate position input')
        sources[str(position_summary)]=digest(position_summary.read_bytes())
        position_rows=[]
        for row in summary['rows']:
            if row['fraction']!=1.:continue
            values=(row['scan'],row['arm'],row['retained_windows'],f"{row['error_m']:.0f}",
                    row['joint_stationary'],row['boundary'],row.get('calibration_warning',False),row['roof_converged'],
                    f"{row['gradient_east_per100m']:+.2f}",f"{row['gradient_north_per100m']:+.2f}")
            position_rows.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in values)+'</tr>')
        subset_images=''.join(f'<img src="position-summary/{p.name}" alt="Per-scan subset comparison; missing cases shown as gaps">' for p in sorted((output/'position-summary').glob('*-subsets.png')))
        position_overview='''<section class="card"><h2>Completed independent position searches</h2>
<p>This table contains the completed matched Fisher-v2 full-membership runs; the completion checklist states how many scans remain. Best means lowest saved score, not smallest distance from the roof or a certified global minimum. Earlier optimizer results are preserved in the per-scan sections; in particular, N02 has known better-scoring basins than its cold Fisher run.</p>
<table><thead><tr><th>Scan</th><th>RF</th><th>Windows</th><th>Distance (m)</th><th>Jointly stationary</th><th>Boundary</th><th>Calibration warning</th><th>Roof converged</th><th>East /100 m</th><th>North /100 m</th></tr></thead><tbody>'''+''.join(position_rows)+'''</tbody></table>
<p><a href="position-summary/position-summary.csv">Full position/subset table (CSV)</a>. Gradients at unconverged roof fits are conditional derivatives, not certified profile gradients.</p>
<img src="position-summary/nuisance-vs-position.png" alt="Nuisance changes versus position distance for completed scans">
<details><summary>Association subset comparisons</summary>'''+subset_images+'</details></section>'
    prior_sections=[]
    for path in sorted((output/'timing-prior-screen').glob('N*.json')):
        prior=json.loads(path.read_text())
        for source,expected in {**prior['inputs']['sources'],**prior['sources']}.items():
            if digest(Path(source).read_bytes())!=expected:raise ValueError('stale timing-prior screen')
        sources[str(path)]=digest(path.read_bytes())
        prior_sections.append(f'<img src="timing-prior-screen/{path.stem}.png" alt="Actual Gaussian timing-prior width versus position and frequency-fit evidence">')
    if prior_sections:
        screening='''<section class="card"><h2>Actual Gaussian timing-prior sensitivity</h2>
<p>Standard deviations for common and satellite-relative timing are scaled together by 0.5, 1, and 2. Hard bounds and all other settings remain fixed. This varies the model priors, not the association tie-break score. Each case uses the same frozen baseline memberships and three position starts, with 20 seconds per fit.</p>
<p>Likelihood fit, prior cost, and position error are shown separately. Do not compare raw penalized totals across prior widths as a common score. Crosses mark nonstationary results; this is a development-only conditional screen. The validation section reports the separate settings decision.</p>'''+''.join(prior_sections)+'</section>'
    screen_path=output/'hyperparameter-screen/aggregate.json'
    if screen_path.exists():
        screen=json.loads(screen_path.read_text())
        sources[str(screen_path)]=digest(screen_path.read_bytes())
        screening+=f'''<section class="card"><h2>Development association screening</h2>
<p>{len(screen['scans'])} development scans: {html.escape(', '.join(screen['scans']))}. Satellite penalty and residual gate vary independently; calibration and candidate pools remain fixed. Timing-prior and curvature-filter experiments are not included in this first screen. No localization ranking or final hyperparameter choice is implied.</p>
<img src="hyperparameter-screen/association-screen.png" alt="Development penalty and residual gate screening">
<p>A wider gate can increase coverage without providing stronger evidence. The middle panels compare a common 300 Hz residual criterion. All means weight scans equally; locked-test results are excluded.</p></section>'''
    stamp = datetime.now(timezone.utc).isoformat()
    refinement_html=''
    audit_path=output/'refinement-audit/summary.json'
    if audit_path.exists():
        audit=json.loads(audit_path.read_text())
        sources[str(audit_path)]=digest(audit_path.read_bytes())
        details=[]
        for case in audit['scans']:
            for path,expected in case['sources'].items():
                if digest(Path(path).read_bytes())!=expected:raise ValueError('stale refinement distribution input')
            label=case['scan']
            details.append(f'''<details><summary>{label}: {case['raw_candidates']:,} saved hypotheses, {case['canonical_candidates']:,} original alias-canonical candidates, {case['windows']:,} windows</summary>
<img src="refinement-audit/{label}-before-after.png" alt="GLRT refinement before and after">
<img src="refinement-audit/{label}-pair-cutoffs.png" alt="Within-window pair separation at four GLRT cutoffs"></details>''')
        refinement_html='''<section class="card"><h2>Orbit-blind refinement distributions</h2>
<p>All original passing hypotheses were retained. Exact original alias copies are collapsed only for the pair histograms, using frequency, epoch and margin agreement; neither solver inputs nor coverage denominators change. The score cutoffs here are display diagnostics, not newly tuned detector thresholds. Multiple candidates in one window need not be the same signal.</p>'''+''.join(details)+'</section>'
    curvature_rows=[]
    for scan in cohort['scans']:
        for path in sorted((inputs/scan['label']/'seed-timing-v6').glob('selection-curvature-*.json')):
            case=json.loads(path.read_text())
            sources[str(path)]=digest(path.read_bytes())
            for arm in ('fitted-c','zero-c'):
                result=case['arms'][arm]['alternatives']['final']
                values=(scan['label'],case['signature']['cutoff'],arm,len(case['signature']['excluded_satellites']),
                        f"{result['assigned']}/{result['denominator']}",f"{100*result['coverage']:.1f}%",result['satellites'])
                curvature_rows.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in values)+'</tr>')
    curvature_html=('''<section class="card"><h2>Curvature-filter screening</h2>
<p>Exclude an entire satellite when any fitted-c baseline receiver track exceeds the pooled linear/quadratic RMS ratio cutoff. Exclusions are frozen and shared across both RF arms; other satellites remain available to fill gaps. This known-roof, in-sample screen does not establish better position accuracy.</p>
<table><thead><tr><th>Scan</th><th>Cutoff</th><th>RF arm</th><th>Excluded IDs</th><th>Assigned windows</th><th>Coverage</th><th>Selected IDs</th></tr></thead><tbody>'''+''.join(curvature_rows)+'</tbody></table></section>') if curvature_rows else ''
    overview_html=''
    if overview:
        fig,axes=plt.subplots(1,2,figsize=(13,5))
        labels=list(dict.fromkeys(r['scan'] for r in overview))
        xx=np.arange(len(labels))
        for arm,offset,color in (('fitted-c',-.18,'#0072b2'),('zero-c',.18,'#d55e00')):
            selected=[next(r for r in overview if r['scan']==label and r['arm']==arm and r['method']=='alternatives') for label in labels]
            for ax,key,scale in zip(axes,('coverage','satellites'),(100.,1.)):
                bars=ax.bar(xx+offset,[r[key]*scale for r in selected],width=.35,color=color,label=arm)
                ax.bar_label(bars,fmt='%.1f' if key=='coverage' else '%.0f',padding=3,fontsize=8)
                ax.set_xticks(xx,labels);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
        axes[0].set(ylabel='Original passing windows (%)',ylim=(0,105),title='Greedy + replacement + alternatives')
        axes[1].set(ylabel='Satellite count',title='Model complexity')
        axes[1].set_ylim(0,max(r['satellites'] for r in overview)*1.25)
        axes[0].legend()
        fig.suptitle('Completed association comparisons · not a position-accuracy metric',fontsize=15)
        fig.text(.5,.015,'Known-roof conditional association; no confirmed identity or position-accuracy claim. Counts do not include pending scans.',ha='center',fontsize=10)
        fig.tight_layout(rect=(0,.065,1,.92));fig.savefig(output/'association-overview.png',dpi=150);plt.close(fig)
        overview_html='<section class="card"><h2>Association overview</h2><img src="association-overview.png" alt="Completed association coverage and satellite counts by scan"></section>'
    text = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>18-scan GLRT benchmark — {'completed study' if final else 'work in progress'}</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;color:#243247;background:#f4f6fa;margin:0}}main{{max-width:1250px;margin:auto;padding:35px}}h1{{font-size:34px}}h2{{margin-top:38px}}.card{{background:white;padding:24px;border-radius:12px;margin:20px 0}}.warning{{border-left:5px solid #d98400}}table{{border-collapse:collapse;font-size:12px;width:100%}}td,th{{padding:9px;text-align:left;border-bottom:1px solid #dce1e8}}img{{width:100%}}code{{font-size:.9em}}small{{color:#647083}}a{{color:#0072b2}}</style>
<main><small>Offline research · capture-bound 40° fixture · {html.escape(stamp)}</small>
<h1>From GLRT activity to defensible satellite associations</h1>
<p>Two historical references plus sixteen additional 2.5 MS/s scans. The study asks whether improved association coverage also improves independent-scan localization, and which settings generalize.</p>
<section class="card warning"><strong>{'Completed bounded study — not a validated localization system.' if final else 'Work in progress — not a completed model comparison.'}</strong>
<p>Metadata cohort: 18/18. Exported inputs: {len(available)}/18. Full refinements in the corrected input namespace: {completed}/18.
Completed association comparisons: {len(pilot_sections)}/18. {'All required per-scan and subset experiments are included; failed fits and boundary results are retained rather than disguised as accurate positions.' if final else f'Full-membership position runs: {complete_positions}/18. Complete subset matrices: {complete_subsets}/18. The report remains a draft until the full experiment matrix and delivery audit are complete.'} The validation section records the settings decision; an inconclusive baseline reference is not proof of optimal hyperparameters.</p></section>
{overview_html}
{leaderboard_section(output,sources)}
{refinement_html}
{heldout_section(output,sources)}
{''.join(pilot_sections)}
{screening}
{finalist_section(output,sources)}
{position_overview}
{curvature_html}
<section class="card"><h2>1. Cohort and evaluation design</h2>
<p>All sixteen additions have verified 2.5 MS/s manifests and cryptographically bound LT3D-004B pose metadata. A remains the original 10 MS/s reference; B is 2.5 MS/s. Selection uses metadata only, excludes prior exported localization subjects, uses distinct three-hour UTC blocks and enforces a thirty-minute inter-capture gap. Splits are balanced across temporal quartiles: eight development, four validation, four locked test. A/B are regression references, not held-out evidence.</p>
<p>The operator roof coordinates are {cohort['known_roof_lat_lon']}. This is not a surveyed ground truth; altitude is unknown. Nominal RX0 west/RX1 east directions and the 40° included mounting angle are not measured beam patterns or a hard hemisphere gate.</p>
<img src="cohort-and-inputs.png" alt="Cohort timing and input window counts">
<div style="overflow-x:auto"><table><thead><tr><th>Scan</th><th>Session</th><th>Role</th><th>Capture time (Pacific)</th><th>MS/s</th><th>Passing candidates</th><th>Passing windows</th><th>Refinement</th></tr></thead><tbody>{''.join(table)}</tbody></table></div></section>
<section class="card"><h2>2. Processing and accounting</h2>
<p>Public read-only capture ports supply immutable original passing hypotheses. Exact alias copies are preserved in these candidate counts; they are not extra GLRT windows. Refinement uses only each candidate's saved frequency, epoch and raw 20 ms IQ. It tests neighboring alias lifts, recenters frequency, and refines fractional epoch in three bounded iterations. Unsuccessful refinements retain the original estimate and an explicit failure flag.</p>
<p>The baseline selects the highest <em>refined</em> GLRT margin per receiver/channel/probe. Alternatives remain available for a separate association arm. Each passing window contributes at most one unit to the coverage objective, even when multiple candidates or simultaneously active satellites are present.</p>
<p>Preflight checks only three retained IQ visits per scan, not the whole payload. Full refinement verifies each used visit as it is read. Acquisition-event IDs are explicitly mapped to retained-IQ ordinals; gaps must never silently select a neighboring visit.</p></section>
<section class="card"><h2>What the models actually optimize</h2>
<p>A 20 ms probe is a receiver/channel observation window. Its acquisition may produce several frequency/epoch hypotheses, each with its own GLRT margin. The margin is a ranking statistic, not a calibrated probability of satellite identity. Refinement tests each saved hypothesis independently using IQ and its own starting frequency/epoch; no satellite orbit guides that refinement. The 0, 0.025, 0.2 and 0.6 cutoffs in the distribution figures are diagnostics, not extra solver thresholds.</p>
<p>After refinement, the primary observation is the highest-margin hypothesis in each originally passing window. The alternatives method can substitute another saved hypothesis, but it cannot increase the denominator or credit the same window twice. Different satellites may be active at the same time in different receiver/channel windows. This prototype deliberately does not claim multiple independently explained signals from one window; such a model would need a separate physical-peak accounting rule.</p>
<table><thead><tr><th>Stage</th><th>Objective</th><th>Meaning</th></tr></thead><tbody>
<tr><td>Satellite selection</td><td>Maximize <code>explained windows − 10 × selected satellites</code></td><td>A discrete coverage/complexity score, not a smooth position likelihood.</td></tr>
<tr><td>Position profiling</td><td>Minimize soft finite-set negative log likelihood + timing priors</td><td>Frozen observation membership and candidate bank; receiver/timing/RF nuisance parameters refitted at each location. The gradient figures refer to this score.</td></tr>
</tbody></table>
<h3>Greedy, replacement and alternatives</h3>
<ol>
<li>Propagate the archived visible catalogue and discover bounded satellite-timing modes against the calibrated measurements. The shared candidate pool includes modes proposed in either RF arm.</li>
<li>For each mode, count currently unexplained windows within the residual tolerance, enforcing receiver/channel track support: at least 10 windows, at least 5 seconds of span, and no gap over 5 seconds within a supported segment.</li>
<li>Greedy selection adds the highest marginal-gain satellite while its new window count exceeds the satellite penalty. Other modes are updated after those windows become owned.</li>
<li>Replacement removes one selected satellite, frees its windows, and greedily tries one or more other satellites. A replacement is accepted only if the discrete objective strictly improves. Up to three repair passes are attempted; this is not exhaustive combinatorial optimization.</li>
<li>The alternatives variant repeats selection with all saved candidate hypotheses available, preserving one credited candidate per window. Extra candidate records are not extra evidence.</li>
</ol>
<h3>Frequency and nuisance model</h3>
<p>The predicted frequency for candidate <code>i</code> and satellite <code>s</code> is</p>
<pre style="overflow-x:auto">D_s(x, t_i + τ + δ_s; F_i) + a_RX + b_RX (t_i − 150 s)
    + c (F_i − F_ref)/(1 GHz) + q_RX(t_i)</pre>
<p><code>D_s</code> is orbit Doppler at the candidate's RF frequency. <code>a_RX</code> and <code>b_RX</code> are receiver offset and linear drift; <code>c</code> is a learned RF-dependent coefficient. <code>q_RX</code> is the frozen, cross-fitted nonlinear receiver correction, interpolated in time from 30-second knots. A single offset is therefore not the whole receiver model. Alias-aware residuals account for the 227.273 kHz frequency periodicity.</p>
<p>The baseline timing prior has a 10-second Gaussian standard deviation on the common timing shift and a 1-second standard deviation on each satellite's mean-centered relative timing. The common shift is bounded to ±10 seconds and total satellite shifts to ±20 seconds. Development tests scale both Gaussian widths by 0.5 or 2 while retaining the hard bounds. The association mode tie-break parameter is distinct from this actual Gaussian prior.</p>
<p>For position comparisons, both RF arms use the fitted-c association's frozen windows and the union of satellite candidates from both association arms. Only <code>c</code> is fixed to zero in the ablation; observations, other priors, nonlinear receiver correction, position starts and maximum fit budgets are matched. Removing <code>c</code> may worsen frequency fit without worsening position, or vice versa.</p>
<h3>Independent 2 km searches and subset interpretation</h3>
<p>Each scan starts at its own known-roof reference. The position design contains 16 reproducible, area-uniform random probes across radial/angular strata, cardinal probes at 50 and 100 m, and eight 2 km boundary points. The roof and two separated low-score probe locations seed local position optimization. Nuisance fits are transferred in both directions between the best location and the roof; 50/100 m finite differences check the local score gradient. No locations are jointly estimated across scans.</p>
<p>The three subset rankings retain 25%, 50%, 75% or 100%: lowest satellite RMS, most windows per satellite, and highest refined window GLRT margin. The first two retain a fraction of satellites; the third retains a fraction of assigned windows. The full 100% case is identical and computed once. Roof-RMS ranking and the curvature filter use the known position, so these are oracle-conditioned diagnostics, not deployable blind association rules.</p>
<p>A cross marks an ineligible numerical/calibration result; a boundary hit is not an interior minimum. A low-distance failed start is not a successful localization. Multiple starting points can find different local minima, and older separately labelled N02/N05 numerical audits retain better or better-converged basins without silently replacing the matched-budget cohort runs.</p>
</section>
<section class="card"><h2>3. Matched model comparisons</h2>
<p>Greedy, greedy plus removal/replacement, and greedy/replacement with alternatives maximize explained windows minus a satellite penalty (baseline 10). Candidate generation searches the visible non-debris catalogue, rather than a seed whitelist. The archived TLE policy for this new comparison is the latest snapshot collected strictly before each scan; historical A/B figures used other snapshot choices and are not silently treated as same-input controls.</p>
<p>Each scan has its own position and nuisance fit inside a 2 km disk. Matched fitted-c and c=0 arms use identical observations, candidates, other priors and search budgets. Best-found minima, boundary hits and restart ambiguity are reported separately. The three subset rankings and four retained fractions reproduce the requested diagnostic design; a ranking computed using the known roof is labeled an oracle diagnostic, not blind inference.</p>
<p>Development screening varies penalties, residual gates, timing-prior scales, curvature filters and alternative handling in stages. Validation chooses a small finalist set. Locked-test localization remains unopened until settings are frozen. The leaderboard separates position error, held-out frequency fit, fixed-denominator coverage, model complexity and runtime; scans receive equal weight.</p></section>
<section class="card"><h2>4. Completion checklist</h2>
<table><thead><tr><th>Deliverable</th><th>Completed scans</th></tr></thead><tbody>
<tr><td>Input export and orbit-blind refinement</td><td>{completed}/18</td></tr>
<tr><td>Three association methods, both RF arms and orbit figures</td><td>{len(pilot_sections)}/18</td></tr>
<tr><td>Independent full-membership 2 km position runs, both RF arms</td><td>{complete_positions}/18</td></tr>
<tr><td>All three subset rankings × four fractions, both RF arms</td><td>{complete_subsets}/18</td></tr>
</tbody></table>
<p>Completed means the bounded run produced its evidence, not that it converged or found the global minimum. Failed fits, search boundaries and calibration warnings remain visible. {'All four held-out result sets are included, with no settings changes based on their outcomes.' if final else 'Published full-membership results do not imply that the reduced-subset comparisons are complete; use the counts above.'}</p>
<p><a href="protocol.json">Protocol</a> · <a href="cohort-v2.json">Frozen cohort</a> · <a href="report-receipt.json">Render provenance</a></p></section>
</main></html>'''
    (output/'report.html').write_text(text)
    receipt = dict(status='complete' if final else 'in_progress', rendered_utc=stamp, scans=18, exported_scans=len(available),
                   complete_refinements=completed, input_root=str(inputs), sources=sources,
                   completed_pilot_association_scans=len(pilot_sections),
                   outputs={'report.html':digest((output/'report.html').read_bytes()),
                            'cohort-and-inputs.png':digest((output/'cohort-and-inputs.png').read_bytes())})
    (output/'report-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('sources','outputs')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--final',action='store_true',help='Requires a fresh complete requirement-level evidence audit before publishing')
    args = parser.parse_args()
    render(args.inputs, args.output,args.final)
