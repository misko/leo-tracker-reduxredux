"""Make lean reproducible detection figures and explicit cell accounting."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
data = json.loads((HERE/'results.json').read_text())
panel = json.loads((HERE/'panel.json').read_text())
rows = [dict(case=slot['request_id'].split('-CH')[0], **row)
        for slot in data['rows'] for outcome in slot['outcomes'] for row in outcome['rows']]
for row in rows:
    if row['label']=='wrong_sequence':
        # Worker constructed this -6 dB signal before evaluate(None), so no
        # second exact-sequence overlay was added. Normalize reporting only.
        baseline=next(r for r in rows if r['case']==row['case'] and r['channel']==row['channel']
            and r['receiver']==row['receiver'] and r['label']=='clean_noise' and r['strength_db'] is None)
        row['strength_db']=-6
        row['background_mean_complex_power_native']=baseline['background_mean_complex_power_native']
        row['injection_mean_complex_power_native']=baseline['background_mean_complex_power_native']*10**(-.6)
recorded = [r for r in rows if r['label']=='recorded' and r['strength_db'] is not None]
grid = [-24, -18, -12, -6]


def count(group):
    return dict(n=len(group), anchor_pass=sum(r['anchor_pass'] for r in group),
        blind_recovered=sum(r['blind_recovered'] for r in group),
        any_gatepass=sum(r['any_gatepass'] for r in group),
        anchor_pass_blind_miss=sum(r['anchor_pass'] and not r['blind_recovered'] for r in group),
        anchor_fail_blind_miss=sum(not r['anchor_pass'] and not r['blind_recovered'] for r in group))


summary = dict(seconds=data['seconds'], expected_recorded_injection_cells=64,
    observed_recorded_injection_cells=len(recorded),
    expected_physical_windows=8, physical_windows=len(data['rows']),
    physical_failures=[dict(request_id=r['request_id'],error=r.get('error')) for r in data['rows'] if r['status']!='complete'],
    parity_all_passed=all(all(v['all_passed'] for v in r.get('receipt',{}).get('parity',{}).values())
        and bool(r.get('receipt',{}).get('parity')) for r in data['rows']),
    runtime_identity_unchanged=data['runtime_identity_unchanged'],
    strength={str(db):count([r for r in recorded if r['strength_db']==db]) for db in grid},
    controls={label:{str(db):count([r for r in rows if r['label']==label and r['strength_db']==db])
        for db in [None]+grid} for label in ['clean_noise','wrong_sequence']},
    per_RX_channel={f'RX{rx}_CH{ch}':{str(db):count([r for r in recorded if r['receiver']==rx and r['channel']==ch and r['strength_db']==db])
        for db in grid} for rx in [1,2] for ch in [1,4,7,8]},
    native_edges=sorted({r['edge'] for r in recorded}),
    controls_reuse_same_two_independent_noise_realizations_across_edges=True,
    baseline_recorded_any_gatepass=sum(r['any_gatepass'] for r in rows if r['label']=='recorded' and r['strength_db'] is None),
    baseline_recorded_RX_cells=sum(r['label']=='recorded' and r['strength_db'] is None for r in rows))
errors=[]
for r in recorded:
    timing_matches=[c for c in r['candidates'] if c['passed_fractional_margin_gate'] and abs(c['timing_error_samples'])<=2]
    if timing_matches:
        errors.append(min(timing_matches,key=lambda c:c['candidate_rank'])['cfo_error_hz'])
summary['first_rank_timing_matched_cfo_errors_hz'] = dict(n=len(errors),
    median=float(np.median(errors)) if errors else None,
    median_absolute=float(np.median(abs(np.asarray(errors)))) if errors else None,
    maximum_absolute=float(max(map(abs,errors))) if errors else None)
diagnostic=json.loads((HERE/'diagnostic.json').read_text())
summary['coarse_trace']=dict(request_id=diagnostic['request_id'],seconds=diagnostic['seconds'],
    export_parity=diagnostic['all_export_parity_passed'],rows=[dict(receiver=i+1,
        coarse_grid_CFOs=len(t['coarse_CFO_grid']),timing_cells=t['timing_cells'],
        local_peaks=t['total_local_peaks'],best_truth_local_peak=t['best_truth_neighborhood_local_peak'],
        best_truth_peak_pre_NMS_rank=t['best_truth_local_peak_unconstrained_score_rank'],
        truth_original8=t['truth_in_original8'],truth_diagnostic256=t['truth_in_top256'])
        for i,t in enumerate(diagnostic['trace'])])
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

columns=['case','channel','receiver','edge','label','strength_db','background_mean_complex_power_native',
         'injection_mean_complex_power_native','waveform_scale_native','anchor_pass','blind_recovered','any_gatepass',
         'anchor_margin','anchor_tracking_cfo_hz','nearest_timing_error_samples','nearest_cfo_error_hz']
with (HERE/'cells.csv').open('w') as f:
    out=csv.DictWriter(f,fieldnames=columns);out.writeheader()
    for row in rows:
        flat={k:row.get(k) for k in columns}
        flat.update(anchor_margin=row['anchor']['margin'],anchor_tracking_cfo_hz=row['anchor']['tracking_cfo_hz'])
        if row['nearest_candidate']:
            flat.update(nearest_timing_error_samples=row['nearest_candidate']['timing_error_samples'],
                        nearest_cfo_error_hz=row['nearest_candidate']['cfo_error_hz'])
        out.writerow(flat)

fig,axs=plt.subplots(2,4,figsize=(13,6),sharex=True,sharey=True)
for j,ch in enumerate([1,4,7,8]):
    for i,rx in enumerate([1,2]):
        ax=axs[i,j]
        groups=[[r for r in recorded if r['channel']==ch and r['receiver']==rx and r['strength_db']==db] for db in grid]
        ax.plot(grid,[np.mean([r['anchor_pass'] for r in g]) for g in groups],'o-',label='Known anchor')
        ax.plot(grid,[np.mean([r['blind_recovered'] for r in g]) for g in groups],'s--',label='Blind identity recovery')
        ax.plot(grid,[np.mean([r['any_gatepass'] for r in g]) for g in groups],':',label='Any gatepass',color='gray')
        ax.set_title(f'RX{rx} CH{ch} (2 scans)');ax.grid(alpha=.2);ax.set_xticks(grid);ax.set_ylim(-.05,1.05)
        if j==0:ax.set_ylabel('Fraction / 2 RX-window cells')
        if i==1:ax.set_xlabel('Injected pilot / background (dB)')
axs[0,0].legend(fontsize=8,loc='upper left')
fig.suptitle('Identical samples: known-anchor gate versus complete production blind search')
fig.tight_layout();fig.savefig(HERE/'detection_strength.png',dpi=160);fig.savefig(HERE/'detection_strength.pdf');plt.close(fig)

fig,axs=plt.subplots(1,2,figsize=(11,4))
for ch,color in zip([1,4,7,8],['#277da8','#43aa8b','#f8961e','#c44949']):
    vals=[r for r in recorded if r['channel']==ch]
    # Small deterministic offsets expose repeated strengths without implying extra precision.
    for n,row in enumerate(vals):
        marker='o' if row['blind_recovered'] else 'x'
        axs[0].scatter(row['strength_db']+(n%4-1.5)*.25,row['anchor']['margin'],color=color,marker=marker,s=30,
            label=f'CH{ch}' if n==0 else None)
axs[0].axhline(.025,color='black',ls='--',lw=1);axs[0].set_xlabel('Injected pilot / recorded background (dB)')
axs[0].set_ylabel('Known-anchor exact minus control score');axs[0].legend(fontsize=8)
axs[0].set_title('o = blind recovery; x = miss')
if errors:axs[1].hist(errors,bins=np.linspace(-100,100,21),color='#277da8')
axs[1].set_xlabel('Exported finalized CFO minus injected CFO (Hz)');axs[1].set_ylabel('RX-strength cells')
axs[1].set_title('First original rank passing gate and timing tolerance')
fig.tight_layout();fig.savefig(HERE/'anchor_and_cfo.png',dpi=160);fig.savefig(HERE/'anchor_and_cfo.pdf');plt.close(fig)

fig,ax=plt.subplots(figsize=(8,4))
x=np.arange(2)
for offset,key,label,color in [(-.25,'truth','Best truth-neighborhood peak','#277da8'),
                               (0,'top8','8th retained coarse peak','#f8961e'),
                               (.25,'top256','256th diagnostic peak','#aaa')]:
    values=[t['best_truth_neighborhood_local_peak'][0] if key=='truth' else
        t['original_NMS'][-1][0] if key=='top8' else t['diagnostic_top256_NMS'][-1][0] for t in diagnostic['trace']]
    ax.bar(x+offset,values,width=.24,label=label,color=color)
ax.set_xticks(x,['RX1','RX2']);ax.set_ylim(.145,.18);ax.set_ylabel('Coarse normalized anchor score (truncated axis)')
ax.set_title('CH8 DS24-0011, -24 dB: true basin absent from coarse nominees')
ax.legend(fontsize=8);fig.tight_layout();fig.savefig(HERE/'coarse_mechanism.png',dpi=160);fig.savefig(HERE/'coarse_mechanism.pdf');plt.close(fig)

lines=['# Detection injection findings','',
f"All {len(data['rows'])}/8 paired windows completed with full unmodified historical candidate parity; {len(recorded)}/64 recorded injection RX-strength cells. Elapsed batch {data['seconds']:.1f} seconds, BLAS1, 580-second alarm. Runtime identity unchanged: {data['runtime_identity_unchanged']}.",'',
'Date/inventory selection: DS24-0010 and0011 in the existing 2026-10-24 analysis inventory; nearest full-scan midpoint per CH1/4/7/8, both RX. Lower and upper pilot edges are represented. No candidate outcome or GPS entered selection or inference.','',
'| Pilot/background dB | Known-anchor pass /16 | Blind identity recovery /16 | Anchor pass, blind miss | Any blind gatepass /16 |',
'|---:|---:|---:|---:|---:|']
for db in grid:
    a=summary['strength'][str(db)]
    lines.append(f"| {db} | {a['anchor_pass']} | {a['blind_recovered']} | {a['anchor_pass_blind_miss']} | {a['any_gatepass']} |")
lines += ['',
'The matched known anchor uses exactly the same complex64 injected samples as the complete blind search and the same 0.025 exact-minus-control gate. Identity recovery additionally requires timing within two native samples modulo exact 750-Hz repetition and finalized CFO within 100 Hz. Any gatepass can instead belong to a pre-existing pilot or an unrelated search candidate.', '',
'Anchor-supported blind misses identify acquisition/search loss for this injected flat-channel signal. Failure at the true anchor shows that this scoring lane does not admit the signal at that strength/background. This finite superposition experiment cannot assign natural CH7/8 yield differences to one cause across the corpus; high injection can mask or interfere with pre-existing signals. Measured reference power includes every signal, noise, DC, and interference component in the native recorded window. It is not physical antenna-input SNR.', '',
f"Recorded zero-injection baseline: any gatepass in {summary['baseline_recorded_any_gatepass']}/{summary['baseline_recorded_RX_cells']} RX cells. These are not false alarms because recordings may contain genuine pilots.",'',
'Every RX/channel has the same coarse-grid transition: known-anchor 2/2 and blind 0/2 at -24 dB, then both 2/2 at -18/-12/-6 dB. Thus matched flat-pilot injections expose acquisition/search sensitivity below the blind threshold, with no CH7/8-specific deficit resolved on this small panel and six-dB grid. Clean Gaussian controls show the same transition. This does not exclude weaker natural pilots, colored/interfering backgrounds, multipath, or a transition difference between tested strengths.','',
'Injection occurs in native ADC samples after the RF chain, and strength is normalized separately to each RX-window background. It therefore cannot test antenna/LNB/front-end frequency-dependent gain or loss, or compare physical antenna-input detection thresholds. A natural CH7/8 signal can be weaker before this injection point while the digital detector responds identically to these matched ratios.','',
'The one predeclared mechanism replay (last frozen slot, DS24-0011 CH8, both RX, -24 dB) reproduced saved injection exports exactly. Production searched 21 coarse CFO values times 13333 timing cells and retained eight nonmaximum-suppressed peaks. The best true-neighborhood local peak had coarse score 0.156400 / 0.155984, ranking 6808th / 7700th among 48367 / 48415 local peaks before suppression. Neither true neighborhood reached the original eight or diagnostic top256 coarse nominees; the eighth selected scores were 0.169560 / 0.170272. Thus these two misses occur at coarse acquisition retention, before fine CFO, candidate ordering, fractional timing or GLRT admission. The saved exports also have no final candidate within two samples of injected timing in all16 -24 dB cells, but only the two traced cells resolve the upstream mechanism.','',
'The diagnostic extra256 proposal ranking never refined or admitted extra candidates. Exact-anchor scoring profiles the usual GLRT residual CFO at known timing/center; it bypasses coarse multiplicity and acquisition budget. Anchor success is not deployable blind recovery, independent detection validation, or equal-false-alarm-rate evidence. No threshold or whitening sweep was performed.','',
'Clean controls use independent complex Gaussian noise across the two receivers, holding realizations across strengths and reusing them across edges. Noise-only produced 0/4 any gatepasses; the four RX-edge outcomes are only two underlying independent noise realizations, so false-alarm precision is weak. Wrong-sequence roll17 produced 0/4 passes at the original anchor but 4/4 blind gatepasses at approximately +748 native samples = 17 symbols. A rolled sequence is a retiming ambiguity for blind acquisition, not a clean null/FPR control. The worker constructs that wrong signal at -6 dB before calling evaluate with no additional injection; raw strength_db=None denotes no second overlay, and report.py labels its effective -6 dB strength explicitly. See summary.json for all strengths, cells.csv for per-RX/channel measurements and results.json for every exported candidate and parity check.','',
f"First-original-rank timing-matched gatepass CFO errors, one per RX-strength cell (no CFO-error selection): {summary['first_rank_timing_matched_cfo_errors_hz']}.",'',
'No position/localization claim, no production edit, no new RF collection, no raw IQ copied. Reader authority and IQ digests remain in panel/results receipts. The first metadata adapter failure and correction were preserved before IQ access; no visit was replaced.','',
'Reproduce with the repository .venv Python and PYTHONPATH=/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src; set OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1. Metadata/IQ reads require the pre-existing privileged filesystem access (`sudo -n env ... study.py run`). Existing protocol.json must remain bound to original source hashes. `test_study.py` owns analytic-template, native-power, exact-period timing and noiseless known-anchor tests. Run `report.py` on results.json to regenerate CSV/figures.']
(HERE/'FINDINGS.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2))
