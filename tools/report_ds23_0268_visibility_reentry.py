"""Report-only geographic evaluation of bounded causal DS23-0268 debugging."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from debug_ds23_0268_visibility_reentry import OUT,replay
from investigate_ds23_0268_remaining_tracks import OUT as PREVIOUS,load
from probe_ds23_frequency_events import OUT as EVENTS
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error
from plot_ds23_0268_remaining_tracks import alias_lines

SELECTED='interior_add_66797'


def graph_piece_prediction(piece,times):
    return np.polynomial.legendre.legval((np.asarray(times)-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])


def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=180,bbox_inches='tight');fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight');plt.close(fig)


def evaluation():
    coverage=read(OUT/'trial_coverage.json');metrics=[]
    for row in coverage['rows']:
        record=read(OUT/'trials'/(row['name']+'.json'))
        for arm,result in record['arms'].items():
            metrics.append(dict(name=row['name'],arm=arm,paired_valid=row['paired_valid'],
                associated_points=row['arms'][arm]['associated_original_winners'],
                associated_percent=row['arms'][arm]['associated_original_percent'],
                tracks=row['arms'][arm]['associated_tracks'],error_km=position_error(result['endpoint_latlon']),
                minimum_gate_slack=result.get('minimum_gate_slack'),phase_change_s=result['final_phase_change_s'],
                objective=result['negative_twice_elbo']))
    with (OUT/'comparison.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(metrics[0]));writer.writeheader();writer.writerows(metrics)
    selected=next(row for row in coverage['rows'] if row['name']==SELECTED)
    if not selected['paired_valid']:raise ValueError('selected model must pass both c arms')
    record=read(OUT/'trials'/(SELECTED+'.json'));before=read(EVENTS/'DS23-0268/receiver_reentry_coverage.json')
    checks={}
    for arm,r in selected['arms'].items():
        old_ids=set(before['arms'][arm]['associated_observation_ids']);new_ids=set(r['associated_observation_ids'])
        checks[arm]=dict(original_associated_points_retained=old_ids<=new_ids,added_unique_points=len(new_ids-old_ids),
            lost_points=len(old_ids-new_ids),goal_pass=r['associated_original_winners']>=2216,
            original_calibration_and_predictive_gates_pass=all(t['compatible'] for t in record['arms'][arm]['gates']['tracks']+record['arms'][arm]['linear_gates']),
            phase_converged=record['arms'][arm]['final_phase_change_s']<=.01,
            minimum_original_gate_slack=record['arms'][arm]['minimum_gate_slack'])
        if not all(checks[arm][k] for k in ('original_associated_points_retained','goal_pass','original_calibration_and_predictive_gates_pass','phase_converged')):
            raise ValueError('acceptance or retention audit failed')
    write(OUT/'selected_result.json',dict(name=SELECTED,record_sha256=sha(OUT/'trials'/(SELECTED+'.json')),checks=checks,
        selection='coverage goal plus original paired gates; stricter interior preferred to boundary-only variant',
        reference_used_for_error_reporting_only=True,GPS_or_future_TLE_used_by_fitter=False,
        raw_objectives_not_compared_between_different_masks_or_powers=True))
    return metrics,selected


def glrt_figure(selected):
    observations=read(SOURCE/'DS23-0268/observations.json');tracks=read(SOURCE/'DS23-0268/tracks.json')
    initial=read(EVENTS/'DS23-0268/receiver_reentry_coverage.json')['arms']['c0'];old=set(initial['associated_observation_ids'])
    current=selected['arms']['c0'];owned=set(current['associated_observation_ids'])
    accepted={r['component'] for r in current['accepted_rows']};fig,axes=plt.subplots(4,4,figsize=(22,14))
    for rx in (1,2):
        for ch in range(1,9):
            ax=axes[(rx-1)*2+(ch-1)//4,(ch-1)%4];points=[o for o in observations if o['receiver']==rx and o['channel']==ch]
            times=np.asarray([o['time_s'] for o in points]);values=np.asarray([o['measured_cfo_hz'] for o in points]);lo,hi=values.min()-8000,values.max()+8000
            for t in tracks:
                if t['receiver']!=rx or t['channel']!=ch:continue
                for piece in t['pieces']:
                    grid=np.linspace(piece['start_s'],piece['end_s'],150)
                    prediction=graph_piece_prediction(piece,grid)
                    for line in alias_lines(prediction,lo,hi):ax.plot(grid,line/1000,color='#9caaa5' if t['key'] in accepted else '#c08591',lw=.6,alpha=.55)
            for kind,color,label in (('old','#267b44','Previously associated'),('new','#277cce','Newly associated'),('unknown','#e04e68','Unassociated')):
                use=np.asarray([('old' if o['observation_id'] in old else 'new' if o['observation_id'] in owned else 'unknown')==kind for o in points])
                ax.scatter(times[use],values[use]/1000,color=color,s=10,alpha=.8,label=label)
            ax.set_title(f'RX{rx} CH{ch}');ax.grid(alpha=.12);ax.set_xlim(0,300);ax.set_ylim(lo/1000,hi/1000)
            ax.set_ylabel('Native CFO (kHz)');ax.set_xlabel('Scan time (s)')
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,ncol=3,loc='lower center')
    fig.suptitle('DS23-0268 · Causal retained association: 2,254 / 3,165 = 71.22%\n'
        'All original associated points retained · graph curves unchanged · original paired gates pass',fontsize=16)
    fig.tight_layout(rect=(0,.045,1,.94));save(fig,'final_associated_GLRT')


def identity_figure():
    data=read(OUT/'identity_catalogue_screen.json');fig,axes=plt.subplots(1,3,figsize=(15,5))
    for ax,key,label in zip(axes,('RX1_53923','RX2_53923','all_53923'),('RX1 pair','RX2 quartet','All six curved tracks'),strict=True):
        rows=data['arms']['c0'][key];two=[next(r for r in rows if r['norad']==n) for n in (53923,67953)]
        ax.bar(['53923','67953'],[r['curve_score'] for r in two],color=['#267b44','#9659ad'])
        for k,r in enumerate(two):ax.text(k,r['curve_score'],f"{r['curve_score']:.1f}\nphase {r['phase_s']:.2f}s",ha='center',va='bottom',fontsize=9)
        ax.set_ylim(0,max(r['curve_score'] for r in two)*1.22);ax.set_title(label);ax.set_ylabel('Shared-phase curve score (lower is better)');ax.grid(axis='y',alpha=.15)
    fig.suptitle('Whole causal catalogue: 1,402 candidates · frozen RF calibration and position\n'
        'Compare bars within each panel only · nominal orbit proposals omit fitted orbit modes and phase priors',fontsize=13)
    fig.tight_layout(rect=(0,0,1,.86));save(fig,'53923_identity_comparison')


def report(metrics,selected):
    record=read(OUT/'trials'/(SELECTED+'.json'));sky=read(OUT/'sky_visibility.json');identity=read(OUT/'identity_catalogue_screen.json')
    rows=[]
    baseline=read(EVENTS/'DS23-0268/receiver_reentry_coverage.json')['arms']
    fine=next(r for r in read(PREVIOUS/'kernel_coverage.json')['rows'] if r['name']=='fine_kernel_CH7')['arms']
    for name,cover in (('Receiver-step + reentry',baseline),('Finer RX basis + CH7',fine),
                       ('Re-nominate 63963',next(r for r in read(OUT/'trial_coverage.json')['rows'] if r['name']=='add_63963')['arms']),
                       ('Retain 66797 with stricter gate interior',selected['arms'])):
        a,b=cover['c0'],cover['fitted_c'];errors=[]
        if name=='Receiver-step + reentry':errors=[a['error_km'],b['error_km']]
        elif name=='Finer RX basis + CH7':errors=[a['error_km'],b['error_km']]
        else:
            trial=record if name.startswith('Retain') else read(OUT/'trials/add_63963.json')
            errors=[position_error(trial['arms'][arm]['endpoint_latlon']) for arm in ('c0','fitted_c')]
        rows.append(f"| {name} | {a['associated_original_winners']} / {b['associated_original_winners']} | {a['associated_original_percent']:.2f}% | {errors[0]:.3f} / {errors[1]:.3f} |")
    text=['# DS23-0268: causal association beyond 70%, 53923 identity and sky geometry','',
        '**Result: 2,254/3,165 original GLRT points associated (71.216%) in both c arms.** All 2,111 earlier associations, '
        'all original curved/predictive position evidence and every original acceptance threshold are retained. '
        'No future TLE or supplied GPS enters fitting or trial selection. Frozen ALGO02 sources remain unchanged.','',
        '| Branch | Associated c0 / fitted-c | c0 fraction | Position error c0 / fitted-c km |',
        '|---|---:|---:|---:|',*rows,'',
        'The 63963 and 66797 rows are alternative branches, not cumulative gains. Geographic error is evaluated '
        'only in this reporter; higher coverage or a lower RF score is not proof of accurate localization.','',
        '![All GLRT associations](final_associated_GLRT.png)','',
        '## What prevented recovery','',
        'The finer, prior-variance-normalized receiver basis first recovers CH7 T000 as causal 64333. Re-nominating '
        'CH7 T003 from 66355 to 63963 plus a frozen extension reaches 69.79%. Independently, recovering both '
        '66797 curves (RX1 CH4 T006, 18 points; CH5 T005, 49 points) initially fails only the retained 53923 '
        'CH5 T003 slope check: 3.021 against a limit of 3 in c0. Its independently fitted pieces are not the problem.','',
        'The existing unconstrained RF optimizer minimizes a marginal bound; it does not require the residual gates '
        'during descent. We refine the same cold RF hypothesis under the original profile, conditional, alias, '
        'visibility, support and predictive gates. Five phase-refresh rounds and at most 40 SLSQP position '
        'iterations per round preserve the same physical priors, masks and aliases between c arms. The 67 curved '
        'points become jointly compatible; frozen extension adds RX1 CH7 T007, 16 points, to 66797.','',
        'An initial constrained solution sits close to a gate boundary. The selected follow-up instead requests '
        'a stricter 0.01 normalized gate slack inside every original limit. Both original gate replays pass; '
        'the source thresholds are unchanged. This is one-scan development, not an independent validation.','',
        '## Is 53923 wrong?','',
        '**That premise is not established.** Removing 53923 improving GPS error was an influence diagnostic, '
        'not an identity test. All ten associated 53923 graph tracks are single polynomial pieces: no multi-piece '
        'join is demonstrated here. A single piece can still contain an erroneous GLRT observation.','',
        'We re-screen all 1,402 causal catalogue candidates with one shared phase per disputed group over '
        '[-15,+15] s at 0.25 s spacing, holding the RF position and receiver calibration fixed. 53923 is the '
        'best nominal-orbit candidate for the combined six curved tracks and for the RX2 quartet. 67953 is '
        'slightly preferred for the short RX1 pair alone (c0 curve scores 93.9 versus 101.4; fitted-c 95.7 '
        'versus 99.1), a weak preference before phase priors and catalogue-search multiplicity. For all six '
        'curves the c0 scores are about 567.9 for 53923 and 1005.4 for 67953. These are proposal scores '
        'without candidate orbit modes, not posterior identity probabilities or the final joint-fit objective.','',
        '![Identity comparison](53923_identity_comparison.png)','',
        'All tested RX1→67953 substitutions, including adding the 62-point CH2 T005 curve and conservatively '
        'reducing changed-family powers, fail retained 63901 residual gates. Bounded constrained refinements '
        'also do not find accepted alternatives; that is not a proof that no feasible alternative exists. '
        'The independent catalogue screen still ranks 63901 first for its two curves.','',
        'Existing simultaneous winning-frame evidence contains one direct RX1 CH1/RX2 CH1 overlap for the '
        '53923 group at 242.3544 s. Its frame-epoch difference is -5.68 ns, consistent with a common emitter '
        'rather than providing positive support for splitting the RXs. It is only one overlap; unknown group '
        'delay and epoch ambiguity prevent treating it as a unique satellite fingerprint. No new IQ was collected.','',
        'The 53923 fit still needs a comparatively large mean-motion-mode coefficient (roughly four times '
        'its engineering prior scale). This flags orbit/radio-model tension; that prior scale is not a '
        'calibrated statistical confidence interval. It does not by itself establish a wrong transmitter.','',
        '## Sky verification','',
        'The scan radio serial matches the station record for LT3D-004B. The record says RX1 west, RX2 east; '
        'a level base implies 70° elevation for each axis. Physical connector mapping is provisional, installed '
        'elevation and RF beam pattern are unmeasured. The station file location is deliberately excluded '
        'from RF inference; azimuth/elevation below uses the fitted RF location.','',
        f"All {len(sky['arms']['c0']['rows'])} associated tracks and all 2,254 associated points are above the horizon. "
        f"Maximum separation from the assumed receiver axis is {sky['arms']['c0']['maximum_required_nominal_half_angle_deg']:.2f}°. "
        'There are zero points behind the nominal feed axes. A cone half-angle of 48° would cover all '
        'associations under this nominal pose; the actual antenna pattern has not been measured, so '
        'horizon visibility is verified and antenna visibility remains conditional. No invented beam-width '
        'gate is used to raise association coverage.','',
        'This conclusion also holds for the unadjusted causal TLEs: all associated points remain above '
        f"the horizon, with maximum nominal-axis separation {sky['arms']['c0']['unadjusted_causal_TLE_maximum_half_angle_deg']:.2f}°. "
        'The sky check therefore does not depend on the fitted phase/orbit corrections to make a satellite visible.','',
        'An explicit report-only check at the supplied evaluation coordinate gives the same horizon conclusion: '
        f"minimum elevation {sky['reference_geometry_diagnostic']['c0']['minimum_elevation_deg']:.2f}°, maximum nominal "
        f"off-axis angle {sky['reference_geometry_diagnostic']['c0']['maximum_required_nominal_half_angle_deg']:.2f}°. "
        'Sky direction changes by at most 0.51° relative to the RF estimate. This coordinate is not fed back '
        'to fitting, nomination or association selection. Only four associated points exceed a 45° nominal '
        'cone half-angle; a measured narrower antenna pattern would require revisiting those cases.','',
        '53923 moves southwest → near zenith → northeast during 225–300 s. Earlier detections on the '
        'west-facing RX1 and later detections on east-facing RX2 are plausible. The axes are only 40° '
        'apart, not opposite horizontal beams. Their near-zenith fields can overlap. 67953 also passes '
        'near zenith, so this geometry does not uniquely distinguish the identities.','',
        '![All associated tracks on the sky](sky_selected_71percent_c0.png)','',
        '| Satellite | Associated points RX1 / RX2 | Minimum elevation | Required nominal cone half-angle |',
        '|---|---:|---:|---:|']
    for n in sorted({r['norad'] for r in sky['arms']['c0']['rows']}):
        group=[r for r in sky['arms']['c0']['rows'] if r['norad']==n]
        counts=[sum(r['points'] for r in group if r['receiver']==rx) for rx in (1,2)]
        text.append(f"| {n} | {counts[0]} / {counts[1]} | {min(r['minimum_elevation_deg'] for r in group):.1f}° | {max(r['required_cone_half_angle_deg'] for r in group):.1f}° |")
    text+=['','## Limits and reproduction','',
        'This reaches the requested association target on this scan. It does not resolve all 911 remaining '
        'points, certify every satellite identity, establish measured antenna visibility, or demonstrate '
        'sub-kilometer localization. Strict-gate constrained fits require cohort testing before promotion.','',
        'Sources: `tools/debug_ds23_0268_visibility_reentry.py` stages `trials`, `constrained`, `interior`, '
        '`coverage`, `identity`; `tools/audit_ds23_0268_sky_visibility.py`; this report builder. '
        'Use `PYTHONPATH=src:tools`, single BLAS threads and the repository venv. Constrained stages also '
        'need the existing SciPy installation at `/tmp/algo03-feasible-deps`. Following TLE diagnostics '
        'from the previous study are not inputs to these trials.','',
        '[Selected result and retention checks](selected_result.json) · [All trial metrics](comparison.csv) · '
        '[Sky table](sky_visibility.csv) · [Sky provenance and per-point angles](sky_visibility.json) · '
        '[Whole-catalogue identity screen](identity_catalogue_screen.json) · [Protocol](protocol.json) · '
        '[Constrained refinement protocol](constrained_protocol.json) · [Interior protocol](interior_protocol.json)']
    (OUT/'README.md').write_text('\n'.join(text)+'\n')
    write(OUT/'provenance.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in
        (ROOT/'tools/debug_ds23_0268_visibility_reentry.py',ROOT/'tools/audit_ds23_0268_sky_visibility.py',
         ROOT/'tools/report_ds23_0268_visibility_reentry.py')},
        observations_sha256=sha(SOURCE/'DS23-0268/observations.json'),graph_tracks_sha256=sha(SOURCE/'DS23-0268/tracks.json'),
        selected_fit_sha256=sha(OUT/'trials'/(SELECTED+'.json')),all_original_observation_and_graph_files_unchanged=True,
        tests_recorded_separately=True,all_radio_inputs_existing=True))


if __name__=='__main__':
    metrics,selected=evaluation();glrt_figure(selected);identity_figure();report(metrics,selected)
