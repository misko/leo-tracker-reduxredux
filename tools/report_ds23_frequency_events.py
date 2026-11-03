"""Evaluate frequency-event trials; GPS is used only by this report stage."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_frequency_events import make_event_problem,attach_event_predictive,extend_event_associations
from audit_ds23_algo01_coverage import coverage
from probe_ds23_frequency_events import OUT,ARMS,METHODS,parameters,cached
from probe_algo03_frame_peak_recovery import context,SOURCE
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha

LABELS=dict(baseline='ALGO02',null='No event\n(same added points)',receiver='Shared RX\nstep',
    receiver_RF='RF-scaled RX\nstep',band='Separate band\nsteps',family='Satellite-family\nstep',
    receiver_reentry='Shared RX step\n+ family re-entry')


def audit(case,method):
    output=OUT/case/(method+'_coverage.json')
    if output.exists():return read(output)
    result=read(OUT/case/(method+'.json'))
    scan,node,keep,base,old=context(case);powers,means,model=parameters(scan,base,old)
    ids={o['observation_id'] for o in read(SOURCE/case/'observations.json')}
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    arms={}
    for arm in ARMS:
        saved=result['arms'][arm];x=np.asarray(saved['endpoint_east_north_km'])
        p=make_event_problem(scan,node,np.asarray(result['mask'],bool),arm,np.asarray(saved['phase_reference']),
            powers,means,model,result['events']);attach_event_predictive(p,entries,powers);cached(p)
        difference=float(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])
        if abs(difference)>1e-3:raise ValueError('event endpoint replay changed')
        extended=extend_event_associations(p,x,saved['gates'])
        accepted={r['component']:r for r in extended['tracks']}
        for r in saved['linear_gates']+saved['gates']['tracks']:
            if r['compatible']:accepted[r['component']]=r
        counts=coverage(list(accepted.values()),scan.tracks,ids)
        tracks=[];frequency,elevation=p.conditional_frequency(x);c=p.calculate(x)
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            if p.keep[sl].any():tracks.append(dict(component=row['component'],times=scan.tracks[i]['times'][p.keep[sl]],
                residual_hz=c['conditional_residual_hz'][sl][p.keep[sl]],observation_ids=np.asarray(scan.tracks[i]['observation_ids'])[p.keep[sl]]))
        arms[arm]=dict(**counts,error_km=position_error(saved['endpoint_latlon']),objective_replay_difference=difference,
                      tracks=tracks,accepted_rows=list(accepted.values()))
    result=dict(case=case,method=method,paired_valid=result['paired_valid'],arms=arms)
    write(output,result);return result


def build_audits():
    tasks=[('DS23-0268',m) for m in METHODS+('receiver_reentry',)]
    execution=read(OUT/'cohort_execution.json')
    tasks.extend((r['case'],'receiver') for r in execution['results'] if r.get('accepted'))
    with ProcessPoolExecutor(max_workers=8) as executor:
        for f in as_completed([executor.submit(audit,*t) for t in tasks]):
            r=f.result();print('audited',r['case'],r['method'],flush=True)


def baseline_coverage(case):
    return read(ROOT/'reports/2026_10_20_algo02_ds23_association_error/memberships'/(case+'.json'))['arms']


def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=185,bbox_inches='tight');fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight')
    plt.close(fig)


def evaluate():
    case='DS23-0268';old=read(SOURCE/case/'algo02_result.json');base=baseline_coverage(case)
    rows=[]
    for arm in ARMS:
        rows.append(dict(case=case,method='baseline',arm=arm,paired_valid=True,
            error_km=base[arm]['error_km'],associated_points=base[arm]['associated_original_winners'],
            associated_percent=base[arm]['associated_original_percent'],tracks=base[arm]['associated_tracks'],
            target_RMS_hz=None,original_data_preserved=True,matched_null_gain=None,penalized_gain=None))
    selection=read(OUT/case/'selection.json');null=read(OUT/case/'null.json')
    for method in METHODS+('receiver_reentry',):
        r=read(OUT/case/(method+'.json'));cover=read(OUT/case/(method+'_coverage.json'))
        for arm in ARMS:
            a=r['arms'][arm];c=cover['arms'][arm]
            target=next(t for t in a['gates']['tracks'] if '-RX1-CH3-T000-' in t['component'])
            gain=null['arms'][arm]['negative_twice_elbo']-a['negative_twice_elbo'] if method!='receiver_reentry' else None
            rows.append(dict(case=case,method=method,arm=arm,paired_valid=r['paired_valid'],
                error_km=c['error_km'],associated_points=c['associated_original_winners'],
                associated_percent=c['associated_original_percent'],tracks=c['associated_tracks'],
                target_RMS_hz=target['profile_rms_hz'],original_data_preserved=True,
                matched_null_gain=gain,penalized_gain=gain-selection['search_penalty'] if gain is not None else None))
    with (OUT/'debug_case_comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    execution=read(OUT/'cohort_execution.json');cohort=[]
    for receipt in execution['results']:
        case=receipt['case'];b=baseline_coverage(case)
        policy=read(OUT/case/'policy.json');accepted=policy['accepted']
        event=read(OUT/case/'receiver_coverage.json')['arms'] if accepted else None
        for arm in ARMS:
            c=event[arm] if accepted else b[arm]
            cohort.append(dict(case=case,arm=arm,event_accepted=accepted,
                baseline_error_km=b[arm]['error_km'],policy_error_km=c['error_km'],
                baseline_associated_points=b[arm]['associated_original_winners'],
                policy_associated_points=c['associated_original_winners'],
                baseline_associated_percent=b[arm]['associated_original_percent'],
                policy_associated_percent=c['associated_original_percent']))
    with (OUT/'cohort_comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(cohort[0]));w.writeheader();w.writerows(cohort)
    statistics={}
    for arm in ARMS:
        selected=[r for r in cohort if r['arm']==arm]
        before=np.array([r['baseline_error_km'] for r in selected]);after=np.array([r['policy_error_km'] for r in selected])
        statistics[arm]=dict(scans=len(selected),accepted_events=sum(r['event_accepted'] for r in selected),
            baseline_mean_km=float(before.mean()),policy_mean_km=float(after.mean()),
            baseline_median_km=float(np.median(before)),policy_median_km=float(np.median(after)),
            additional_associated_points=sum(r['policy_associated_points']-r['baseline_associated_points'] for r in selected),
            baseline_mean_associated_percent=float(np.mean([r['baseline_associated_percent'] for r in selected])),
            policy_mean_associated_percent=float(np.mean([r['policy_associated_percent'] for r in selected])),
            improved_scans=int(sum(after<before-1e-6)),worsened_scans=int(sum(after>before+1e-6)))
    write(OUT/'evaluation.json',dict(debug_case=rows,cohort=statistics,
        method_selection_uses_RF_bound_and_paired_gates_not_position_error=True,
        debug_case_excluded_from_20_case_cohort=True,cohort_is_previous_development_set_same_location=True,
        no_future_TLE_or_GPS_association_inputs=True,full_acquisition_or_cold_satellite_discovery_not_rerun=True,
        null_has_same_added_points_but_is_unqualified_and_not_a_policy_position=True,
        report_tool_sha256=sha(ROOT/'tools/report_ds23_frequency_events.py')))
    return rows,cohort,statistics


def plots(rows,cohort,statistics):
    methods=['baseline','null','receiver','receiver_RF','band','family','receiver_reentry']
    fig,axes=plt.subplots(2,2,figsize=(16,10))
    x=np.arange(len(methods));width=.36;colors={'c0':'#257c85','fitted_c':'#a04e9c'}
    for k,arm in enumerate(ARMS):
        data=[next(r for r in rows if r['method']==m and r['arm']==arm) for m in methods]
        bars=axes[0,0].bar(x+(k-.5)*width,[r['error_km'] for r in data],width,
                          color=colors[arm],alpha=.8,label=arm.replace('_',' '))
        for b,r in zip(bars,data,strict=True):
            axes[0,0].text(b.get_x()+b.get_width()/2,b.get_height()+.025,f'{r["error_km"]:.2f}',ha='center',fontsize=8)
            if not r['paired_valid']:b.set_hatch('///');b.set_alpha(.35)
        bars=axes[0,1].bar(x+(k-.5)*width,[r['associated_percent'] for r in data],width,color=colors[arm],alpha=.8)
        for b,r in zip(bars,data,strict=True):
            if not r['paired_valid']:b.set_hatch('///');b.set_alpha(.35)
    for ax in axes[0]:
        ax.set_xticks(x,[LABELS[m] for m in methods],fontsize=8);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    axes[0,0].set_ylabel('Position error (km)');axes[0,0].set_ylim(0,6.25);axes[0,0].legend(fontsize=9)
    axes[0,0].set_title('Frequency-event repair does not cure position bias')
    axes[0,1].set_ylabel('Associated original GLRT (%)');axes[0,1].set_ylim(0,100)
    axes[0,1].set_title('Hatched control fails gates; its trial position is not accepted')
    mask=[r['method'] for r in rows if r['arm']=='c0' and r['method'] not in ('baseline','null','receiver_reentry')]
    gains=[next(r['penalized_gain'] for r in rows if r['method']==m and r['arm']=='c0') for m in mask]
    axes[1,0].bar([LABELS[m] for m in mask],gains,color='#257c85');axes[1,0].axhline(0,color='black',lw=.8)
    axes[1,0].set_ylabel('Same-mask RF bound gain after search penalty')
    axes[1,0].set_title('c = 0 model comparison · amplitude Occam cost is marginalized')
    old=read(ROOT/'reports/2026_10_20_ds23_0268_longest_unassociated/screen.json')
    target=read(ROOT/'reports/2026_10_20_ds23_0268_longest_unassociated/target.json')
    t=np.array(target['times'])
    axes[1,1].plot(t,old['arms']['c0']['frozen']['conditional_residual_hz'],'o-',ms=2,lw=.6,color='#d83252',label='Original model')
    for method,color in [('receiver','#257c85'),('receiver_reentry','#a04e9c')]:
        c=read(OUT/'DS23-0268'/(method+'_coverage.json'))
        tr=next(r for r in c['arms']['c0']['tracks'] if '-RX1-CH3-T000-' in r['component'])
        axes[1,1].plot(tr['times'],tr['residual_hz'],'o-',ms=2,lw=.6,color=color,label=LABELS[method].replace('\n',' '))
    axes[1,1].axhline(0,color='black',lw=.7);axes[1,1].axvline(108.5,color='black',ls='--',lw=.8)
    axes[1,1].set_ylabel('Target conditional residual (Hz)');axes[1,1].set_xlabel('Scan time (s)');axes[1,1].legend(fontsize=8)
    axes[1,1].set_title('All 82 target points retained in qualified event fits')
    for ax in axes[1]:ax.grid(alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('DS23-0268 · Shared frequency-event prototypes · all original position evidence preserved',fontsize=15)
    fig.text(.5,.01,'Four event variants and the no-event control share 136 added curved points. Re-entry adds a further 71-point family.\n'
             'RF fit improvements and association coverage are reported separately from geographic accuracy.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.06,1,.95));save(fig,'DS23_0268_comparison')
    fig,axes=plt.subplots(1,2,figsize=(13,6),sharex=True,sharey=True)
    maximum=max(max(r['baseline_error_km'],r['policy_error_km']) for r in cohort)*1.08
    for ax,arm in zip(axes,ARMS,strict=True):
        data=[r for r in cohort if r['arm']==arm]
        for accepted,color,label in ((False,'#999999','Unchanged / fallback'),(True,'#257c85','Accepted event')):
            selected=[r for r in data if r['event_accepted']==accepted]
            ax.scatter([r['baseline_error_km'] for r in selected],[r['policy_error_km'] for r in selected],
                       color=color,s=45,alpha=.8,label=f'{label} ({len(selected)})')
            if accepted:
                for r in selected:ax.annotate(r['case'][-4:],(r['baseline_error_km'],r['policy_error_km']),xytext=(5,5),textcoords='offset points',fontsize=8)
        ax.plot([0,maximum],[0,maximum],'k--',lw=1);ax.set_xlim(0,maximum);ax.set_ylim(0,maximum)
        ax.set_aspect('equal');ax.set_xlabel('ALGO02 position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8)
        s=statistics[arm]
        ax.set_title(f'{arm} · mean {s["baseline_mean_km"]:.3f} → {s["policy_mean_km"]:.3f} km\n'
                     f'median {s["baseline_median_km"]:.3f} → {s["policy_median_km"]:.3f} km')
    axes[0].set_ylabel('Event-repair policy position error (km)')
    fig.suptitle('20 other DS23 development scans · RF-selected policy with paired gate fallback',fontsize=14)
    fig.text(.5,.01,'Debug scan 0268 excluded. Same recording site; this is not validation at a new location. No original observation is removed.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.92));save(fig,'cohort_position_errors')


def html_report(rows,statistics):
    from html import escape
    current=[]
    for method in ('baseline','receiver','receiver_RF','band','family','receiver_reentry'):
        a=next(r for r in rows if r['method']==method and r['arm']=='c0')
        b=next(r for r in rows if r['method']==method and r['arm']=='fitted_c')
        current.append('<tr>'+''.join(f'<td>{v}</td>' for v in (
            escape(LABELS[method].replace('\n',' ')),a['associated_points'],f'{a["associated_percent"]:.2f}%',
            a['tracks'],f'{a["error_km"]:.3f}',f'{b["error_km"]:.3f}',
            '—' if a['target_RMS_hz'] is None else f'{a["target_RMS_hz"]:.1f}'))+'</tr>')
    cohort=[]
    for arm,s in statistics.items():
        cohort.append('<tr>'+''.join(f'<td>{v}</td>' for v in (
            escape(arm),s['scans'],s['accepted_events'],
            f'{s["baseline_mean_km"]:.3f} → {s["policy_mean_km"]:.3f}',
            f'{s["baseline_median_km"]:.3f} → {s["policy_median_km"]:.3f}',
            s['additional_associated_points']))+'</tr>')
    text='''<!doctype html><html lang="en"><meta charset="utf-8"><title>DS23 frequency-event prototypes</title>
<style>body{font:16px/1.6 system-ui;max-width:1150px;margin:40px auto;padding:0 24px;color:#182530}
img{max-width:100%}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #ccd4da;padding:7px;text-align:left}
th{background:#edf3f6}code{background:#edf3f6;padding:2px 5px}h1,h2{line-height:1.2}a{color:#157080}</style>
<h1>DS23 shared frequency-event prototypes</h1>
<p><strong>Result:</strong> a small shared frequency-event model recovers the complete longest rejected curve in DS23-0268.
It improves association coverage but does not demonstrate improved localization. The RF-selected receiver model slightly
worsens position on this debug case and on the matched 20-scan development comparison. These results do not replace ALGO02.</p>
<h2>Hypotheses and controls</h2>
<p>Four Gaussian event variants are tested: one additive receiver amplitude; one receiver amplitude proportional to RF;
two independent low/high-band receiver amplitudes; and one RF-scaled amplitude per nominated satellite family crossing
the event. On this case the family model has one amplitude. All use a zero-mean 300 Hz amplitude prior. A null model has
the identical added observations without an event. A separate recovery experiment adds the independently checked 71-point
67935 curve; its raw bound is not ranked against the variants with fewer observations.</p>
<p>DS23-0268 contains 3,165 original winning GLRT points. The current 82-point RX1 CH3 curve spans 61.49–120.03 s and was
already nominated as 64923 / STARLINK-34643. The earlier independent test learned an approximately 350–365 Hz event from
170 other-channel points, without the target or another family's 71-point curve. Both held-out curves improved. Saved-IQ
known-pilot refinement preserved the discrepancy. This motivated the full joint tests below.</p>
<h2>RF-only event discovery and position refitting</h2>
<ol><li>Use the frozen scan's GLRT, graph tracks, satellite nominations, aliases, radio noise and strictly causal TLE authority.
No surveyed position or following TLE enters inference. This experiment does not rerun acquisition or cold satellite discovery.</li>
<li>Select the longest wholly unassociated graph curve using original observation IDs. Its receiver and time support define
the focused event search; no receiver number, event time or satellite number is hard-coded.</li>
<li>Screen curved nomination residuals with at least 12 points, span ≥10 s, profile RMS ≤750 Hz, absolute bias ≤3,000 Hz and
positive visibility. A proposal requires at least two channels with at least three measurements on each side. Weighted
per-curve constant and linear terms are projected out only for proposal discovery, so unrelated offsets or smooth rate
errors cannot alone nominate a jump. The actual calibration fit retains its original priors.</li>
<li>Search 2 s event-time proposals, refine near a local candidate at 0.25 s spacing, and penalize the time/model search by
<code>2 log(max(282, tested_times) × 4)</code>. Amplitude complexity and shared uncertainty are integrated in the full model.
The focused case rediscovers 108.5 s and offers 136 additional curved measurements.</li>
<li>Append Gaussian event coordinates to the original nuisance design without changing its original physical coordinates.
Predictive linear observations keep the full shared covariance, including event uncertainty, and do not enter calibration
normal equations. All original position evidence remains present. Cold position fits start at the regional origin in the
original 25 × 25 km box centered at (37.906, −122.545), with five phase updates and 48 position steps per update.</li>
<li>Apply every original profile, conditional residual, alias, visibility, support and phase-convergence gate in both matched
c arms. Rank event models only on the same observation mask using the full c=0 bound plus the search penalty. Fitted c must
pass the same policy gates. The reference coordinate is used only by this reporting tool for geodesic error.</li></ol>
<h2>DS23-0268 results</h2>
<table><tr><th>Method</th><th>Associated GLRT</th><th>Coverage</th><th>Tracks</th><th>c=0 error km</th><th>Fitted-c error km</th><th>Target RMS Hz, c=0</th></tr>'''+''.join(current)+'''</table>
<p>All event rows pass the complete paired gates and preserve the original position evidence. The same-mask no-event control
fails three curves, including the target, and has no accepted policy position. Its trial errors are 5.311 / 5.484 km.
The shared additive receiver event has the best RF bound: a 31.03-unit improvement over the matched null, or 16.97 units after
the search penalty. Adding per-band amplitudes is not supported by this comparison. The family event's small geographic
advantage is not used to select it. Association counts include full frozen-calibration graph extensions and unique original
winning IDs, not just position-evidence points.</p>
<img src="DS23_0268_comparison.png" alt="Debug-case coverage, residuals, score and position comparison">
<h2>20 other DS23 development scans</h2>
<p>The same automatic focused detector and additive receiver model run on the previous 20 development scans; debug case 0268
is excluded. No thresholds are tuned against their geographic errors. Accept a repair only if its same-mask c=0 gain exceeds
the fixed search penalty and every paired gate passes; otherwise retain ALGO02. All 20 remain in the denominator.
This is evidence from one recording site and an existing development set, not validation at a new location.</p>
<table><tr><th>Arm</th><th>Scans</th><th>Accepted repairs</th><th>Mean error km</th><th>Median error km</th><th>Net associated points gained</th></tr>'''+''.join(cohort)+'''</table>
<img src="cohort_position_errors.png" alt="Twenty-scan position comparison with all fallback cases included">
<h2>Interpretation and recommendation</h2>
<p>Keep the simple receiver-step model as an association-repair candidate. It explains a real compatibility failure in the
long curve and passes joint gates without dropping old position evidence. Do not promote this policy as an ALGO03
localization improvement: the controlled mean and median are slightly worse. Additional band parameters do not buy a
demonstrated benefit here.</p>
<p>Frequency-event repair does not resolve the existing satellite-identity, phase/orbit-prior and position-model biases.
A useful next design is to validate proposed events across independent curved families, then investigate their influence
on position separately. Sparse RX2 evidence near the debug event prevents attributing the physical change specifically
to the RX1 LNB/LO rather than a common timing/reference disturbance. The family and receiver event types are not uniquely
identified by this case. One focused event per scan is a bounded prototype, not an exhaustive multiple-event model.</p>
<h2>Validation and artifacts</h2><p>Nine focused tests pass. Original endpoint and zero-scale event replays pass in both c arms.
Linear calibration replay differences are checked; the frozen ALGO02 sources verify unchanged. No new RF collection occurs.
Early uncentered/global proposal experiments remain in separate v1/v2 directories and are excluded from these results.</p>
<ul><li><a href="debug_case_comparison.csv">All debug-case metrics</a></li>
<li><a href="cohort_comparison.csv">All 20-scan metrics</a></li><li><a href="evaluation.json">Machine-readable evaluation</a></li>
<li><a href="cohort_protocol.json">Cohort protocol</a></li><li><a href="cohort_execution.json">Terminal execution receipts</a></li>
<li><a href="DS23-0268/replay.json">Original and zero-event replays</a></li></ul></html>'''
    (OUT/'report.html').write_text(text)


if __name__=='__main__':
    build_audits();rows,cohort,statistics=evaluate();plots(rows,cohort,statistics);html_report(rows,statistics)
    print(statistics,flush=True)
