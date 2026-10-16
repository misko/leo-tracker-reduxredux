from pathlib import Path
import base64, hashlib, html, json, shutil
from datetime import datetime, timezone
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

SOURCE = Path('/tmp/three-track-investigation/space-track-pipeline-rerun')
DEST = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/three-track-20261016')
DEST.mkdir(parents=True, exist_ok=True)
(DEST/'evidence').mkdir(exist_ok=True)
(DEST/'figures').mkdir(exist_ok=True)
(DEST/'scripts').mkdir(exist_ok=True)
def load(name): return json.loads((SOURCE/(name+'.json')).read_text())
comparison=load('comparison'); seeded=load('track_seed_report'); shared=load('shared_band_timing_result')
after=shared['after']; before=shared['before']; transfer=load('rx2_timing_transfer')
prior=load('timing_prior_comparison'); compressed=load('timing_compressed_comparison')
explanation=load('late_explanation_comparison'); controls=load('rx2_guidance_control_summary')
assert [comparison['original']['associated'],comparison['space_track']['associated'],seeded['associated'],after['associated']]==[1643,2150,2627,2666]
assert [t['intended_matches'] for t in after['tracks']]==[26,29,72]
assert transfer['count']==20 and controls['0']['margin_and_frequency_pass']==20
assert sum(v['margin_and_frequency_pass'] for k,v in controls.items() if k!='0')==0

COLORS=['#D55E00','#0072B2','#009E73','#7754A2']
def figure(size):
    fig=Figure(figsize=size,layout='constrained');FigureCanvasAgg(fig);return fig
def save(fig,name):
    fig.savefig(DEST/'figures'/name,dpi=170,facecolor='white')
    fig.savefig(DEST/'figures'/name.replace('.png','.svg'),facecolor='white')
def style(ax): ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)

fig=figure((13,4.9));axes=fig.subplots(1,2)
labels=['Original HF','Space-Track','Track-informed\ninitialization','Experimental\nband correction']
counts=[comparison['original']['associated'],comparison['space_track']['associated'],seeded['associated'],after['associated']]
bars=axes[0].bar(range(4),np.array(counts)/4797,color=COLORS)
for bar,count in zip(bars,counts):axes[0].text(bar.get_x()+bar.get_width()/2,bar.get_height()+.015,f'{count:,} / 4,797\n{count/4797:.1%}',ha='center',fontsize=9)
axes[0].set_xticks(range(4),labels,fontsize=9);axes[0].set(ylabel='Fraction associated',ylim=(0,.68),title='Whole-scan association coverage')
target_labels=['CH2 · 50–75 s\n29 coherent points','CH4 · 40–100 s\n73 coherent points','CH2 · 170–190 s\n27 points']
order=[1,2,0];x=np.arange(3)
stage_tracks=[comparison['original']['tracks'],comparison['space_track']['tracks'],seeded['tracks'],after['tracks']]
for i,tracks in enumerate(stage_tracks):
    vals=[tracks[j]['associated']/tracks[j]['count'] for j in order]
    axes[1].bar(x+(i-1.5)*.19,vals,.19,color=COLORS[i],label=labels[i].replace('\n',' '))
axes[1].set_xticks(x,target_labels,fontsize=9);axes[1].set(ylabel='Fraction associated to any satellite',ylim=(0,1.15),title='The original three target sets');axes[1].legend(fontsize=8,loc='lower right')
for ax in axes:style(ax)
fig.suptitle('Single-scan recovery progression · same 4,797 selected observations\nAssociation gains are in-sample evidence; no ground-truth position accuracy is established',fontsize=12)
save(fig,'01_association_progression.png')

fig=figure((12,4.7));axes=fig.subplots(1,2)
for i,key in enumerate(['before','after']):
    d=shared[key];vals=[d['tracks'][j]['intended_rms_hz'] for j in order]
    bars=axes[0].bar(x+(i-.5)*.34,vals,.34,color=COLORS[[1,3][i]],label=['Tighter-prior baseline','Plus fixed satellite/band correction'][i])
    for b,val in zip(bars,vals):axes[0].text(b.get_x()+b.get_width()/2,val*1.055,f'{val:.0f}',ha='center',fontsize=9)
axes[0].set_xticks(x,['Early CH2 → 69433','CH4 → 69333','Late CH2 → 69522'],fontsize=9);axes[0].set(yscale='log',ylim=(80,4500),ylabel='RMS over every target point (Hz)',title='Residuals against the proposed identity');axes[0].legend(fontsize=8)
labels2=['Late CH2 → 69522','Early CH2 → 69433','CH4 → 69333','Upper 69522 peers']
for i,key in enumerate(['before','after']):
    d=shared[key];vals=[t['intended_matches'] for t in d['tracks']]+[d['upper_69522_matches']];den=[27,29,73,54]
    bars=axes[1].bar(np.arange(4)+(i-.5)*.34,np.array(vals)/den,.34,color=COLORS[[1,3][i]])
    for b,a,n in zip(bars,vals,den):axes[1].text(b.get_x()+b.get_width()/2,b.get_height()+.025,f'{a}/{n}',ha='center',fontsize=9)
axes[1].set_xticks(range(4),labels2,fontsize=8,rotation=12);axes[1].set(ylim=(0,1.18),ylabel='Fraction assigned to proposed identity',title='Upper-band support is retained')
for ax in axes:style(ax)
fig.suptitle('Experimental correction: 69522 / CH1–4 / both receivers · extra orbit-time parameter −0.977083 s\nCorrection selected from the inspected RX1 trajectory; its physical cause remains unresolved',fontsize=11)
save(fig,'02_target_recovery.png')

fig=figure((13,4.7));axes=fig.subplots(1,3);rows=prior+compressed
names=['2 s\noriginal start','1 s\noriginal start','0.5 s\noriginal start','2 s\ncompressed start','0.5 s\ncompressed start']
for ax,key,title,ylabel in [(axes[0],'associated','Association count','Associated observations'),(axes[1],'relative_timing_rms_s','Timing dispersion','RMS relative satellite timing (s)')]:
    vals=[r[key] for r in rows];bars=ax.bar(range(5),vals,color=[COLORS[1]]*3+[COLORS[3]]*2)
    for b,val in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,val+(max(vals)*.015),f'{val:.0f}' if key=='associated' else f'{val:.2f}',ha='center',fontsize=8)
    ax.set_xticks(range(5),names,fontsize=7);ax.set(title=title,ylabel=ylabel,ylim=(0,max(vals)*1.15));style(ax)
vals=[r['audit']['objective'] for r in [prior[2],compressed[1]]];bars=axes[2].bar([0,1],vals,color=[COLORS[1],COLORS[3]])
for b,val in zip(bars,vals):axes[2].text(b.get_x()+b.get_width()/2,val+70,f'{val:,.0f}',ha='center',fontsize=9)
axes[2].set_xticks([0,1],['Original start\n2,764 associations','Compressed start\n2,633 associations'],fontsize=8);axes[2].set(ylim=(54000,61000),ylabel='0.5 s prior objective; lower is better',title='Matched-prior comparison');style(axes[2])
fig.suptitle('Timing prior and initialization both matter · same observations/candidates and 65 s fit allowance\nCommon timing prior stays 3 s; compressed initial shifts use ±3 s, final timing bounds remain unchanged',fontsize=11)
save(fig,'03_timing_prior_initialization.png')

fig=figure((12,4.7));axes=fig.subplots(1,2);modes=['offset','time','scale_offset'];mode_names=['Constant offset\n1 parameter','Timing-shaped\n1 parameter','RF scale + offset\n2 parameters']
for i,split in enumerate(['seed_to_extension','early_to_late','late_to_early']):
    vals=[next(r for r in explanation if r['mode']==mode and r['split']==split)['test_rms_hz'] for mode in modes]
    bars=axes[0].bar(x+(i-1)*.24,vals,.24,color=COLORS[i],label={'seed_to_extension':'27 seed → 11 extension','early_to_late':'Early half → late half','late_to_early':'Late half → early half'}[split])
    for b,val in zip(bars,vals):axes[0].text(b.get_x()+b.get_width()/2,val+8,f'{val:.0f}',ha='center',fontsize=8)
axes[0].set_xticks(x,mode_names,fontsize=9);axes[0].set(ylabel='Prediction RMS on other points (Hz)',ylim=(0,650),title='Temporal transfer on the extended 38-point track');axes[0].legend(fontsize=7)
search=load('extended_lower_full_search')['timing_only'][:5]
bars=axes[1].bar(range(5),[r['rms_hz'] for r in search],color=[COLORS[2]]+[COLORS[1]]*4)
for b,r in zip(bars,search):axes[1].text(b.get_x()+b.get_width()/2,r['rms_hz']*1.05,f"{r['rms_hz']:.0f}",ha='center',fontsize=9)
axes[1].set_xticks(range(5),[str(r['satellite']) for r in search]);axes[1].set(yscale='log',ylim=(90,8000),ylabel='38-point RMS (Hz)',title='Regional candidate search, timing only ±5 s')
for ax in axes:style(ax)
fig.suptitle('69522 is strongly favored within the tested search; correction shape transfers along the trajectory\nExploratory splits share full-scan calibration/position and inspected-track selection; identity is not proven',fontsize=11)
save(fig,'04_late_track_explanations.png')

fig=figure((13,4.7));axes=fig.subplots(1,3);pts=transfer['points'];times=[r['time_s'] for r in pts]
axes[0].scatter(times,[r['before_hz'] for r in pts],label='Shared timing',color=COLORS[1],s=25);axes[0].scatter(times,[r['after_hz'] for r in pts],label='RX1-learned correction',color=COLORS[3],s=25);axes[0].axhline(0,color='gray',lw=.8);axes[0].set(xlabel='Time from scan origin (s)',ylabel='RX2 orbit residual (Hz)',title='20 guided RX2 counterparts');axes[0].legend(fontsize=8)
vals=[transfer['before_rms_hz'],transfer['after_rms_hz']];bars=axes[1].bar([0,1],vals,color=[COLORS[1],COLORS[3]])
for b,val in zip(bars,vals):axes[1].text(b.get_x()+b.get_width()/2,val+45,f'{val:.0f} Hz',ha='center',fontsize=9)
axes[1].set_xticks([0,1],['Shared timing','Fixed RX1 correction'],fontsize=8);axes[1].set(ylim=(0,3300),ylabel='RX2 residual RMS (Hz)',title='No RX2 correction refit')
keys=['0','137','503','997','1499'];vals=[controls[k]['margin_and_frequency_pass'] for k in keys];bars=axes[2].bar(range(5),vals,color=[COLORS[2]]+[COLORS[1]]*4)
for b,val in zip(bars,vals):axes[2].text(b.get_x()+b.get_width()/2,val+.45,f'{val}/38',ha='center',fontsize=8)
axes[2].set_xticks(range(5),['Aligned','+137','+503','+997','+1499'],fontsize=8);axes[2].set(ylim=(0,25),xlabel='Epoch displacement (samples)',ylabel='Passing guided detections',title='Same-window negative controls')
for ax in axes:style(ax)
fig.suptitle('Independent receiver signal support, using RX1-guided epoch/CFO proposals\nGate: margin ≥0.025 and circular CFO difference <1,000 Hz; 0/152 shifted controls is not a calibrated false-alarm rate',fontsize=11)
save(fig,'05_rx2_transfer_controls.png')

for path in sorted(SOURCE.glob('*.json')):shutil.copy2(path,DEST/'evidence'/path.name)
shutil.copy2(SOURCE/'output'/'terminal.json',DEST/'evidence'/'space_track_terminal.json')
for name in ['compare_space_track_pipeline.py','report_track_seed.py','rerun_track_seed_fit.py','shared_band_timing_refit.py','scoped_timing_refit.py','rx2_timing_transfer.py','rx2_guidance_negative_controls.py','late_explanation_comparison.py','replay_extended_late_cfo.py','late_within_frame_scale.py','within_frame_scale_control.py','audit_three_track_exceptions.py','plot_three_track_exceptions.py']:
    path=Path('/tmp')/name
    if path.exists():shutil.copy2(path,DEST/'scripts'/name)
shutil.copy2(__file__,DEST/'scripts'/'build_report.py')
for name in ['late_track_conflict.png','raw_cfo_replay.png','rx1_band_time_profile.png','frame_phase_crossband.png','frame_range_consistency.png','three_track_exceptions.png']:
    shutil.copy2(SOURCE/name,DEST/'figures'/name)
def image(name,caption):
    encoded=base64.b64encode((DEST/'figures'/name).read_bytes()).decode()
    return '<figure><img alt="'+html.escape(caption,quote=True)+'" src="data:image/png;base64,'+encoded+'"><figcaption>'+caption+'</figcaption></figure>'
def ev(name,label=None):return '<a href="evidence/'+name+'.json">'+html.escape(label or name+'.json')+'</a>'
def table(headers,rows):return '<div class="table"><table><thead><tr>'+''.join('<th>'+v+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
parts=[]
parts.append('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Three unassociated trajectories — single-scan investigation</title><style>
:root{font-family:Inter,system-ui,sans-serif;color:#192632;background:#eef2f6;line-height:1.6}body{margin:0}main{max-width:1150px;margin:24px auto;background:white;padding:36px 48px;box-shadow:0 4px 24px #0001}h1{font-size:2.2rem;line-height:1.2;margin:8px 0 16px}h2{border-top:1px solid #d5dde5;padding-top:28px;margin-top:34px;font-size:1.45rem}h3{font-size:1.1rem;margin-top:26px}p{max-width:1000px}.subtitle{color:#536473}.notice{background:#edf4fc;border-left:5px solid #3278ad;padding:14px 20px}.warning{background:#fff5e6;border-left:5px solid #d18429;padding:14px 20px}.table{overflow:auto}table{width:100%;border-collapse:collapse;font-size:.92rem}th{text-align:left;background:#edf2f6}th,td{padding:11px 13px;border-bottom:1px solid #dfe5eb;vertical-align:top}figure{margin:24px 0}img{display:block;width:100%;height:auto}figcaption,.sources{font-size:.85rem;color:#596a79}a{color:#17639c}code{font-size:.86em;overflow-wrap:anywhere}li{margin:8px 0}.tag{font-size:.85rem;letter-spacing:.08em;text-transform:uppercase;color:#17639c;font-weight:700}details{margin:16px 0;padding:10px 16px;border:1px solid #dfe5eb}footer{margin-top:32px;font-size:.85rem;color:#596a79}@media(max-width:750px){main{padding:24px 18px;margin:0}h1{font-size:1.8rem}}@media print{main{box-shadow:none;margin:0;padding:0}figure,table{break-inside:avoid}details{display:none}}</style></head><body><main>
<div class="tag">Research report · 16 October 2026 · saved evidence snapshot</div><h1>Recovering three unassociated trajectories in one fast scan</h1>
<p class="subtitle">Scan <code>fast8-auto-20261016-161535-99008d35-1-lower</code><br>Run <code>fast-9571943d3dccdf4f327e1346d1bf34b8</code> · RX1 = receiver 0; RX2 = receiver 1. All plotted times are seconds from scan origin.</p>
<div class="notice"><strong>Result:</strong> coherent-track initialization recovered the first two trajectories. The third has a strong satellite candidate and a satellite/band correction that transfers to the other receiver. Its physical cause is still unresolved.</div>
<p>Whole-scan association coverage rose from <strong>34.3% to 55.6%</strong> across these experiments: 1,023 additional associated observations, or 21.3 percentage points. These are frequency-fit and association results. No ground-truth position accuracy has been established for this scan, and these diagnostic changes have not been deployed.</p>''')
parts.append('<h2>1. Recovery progression</h2>')
parts.append(table(['Stage','Associated / 4,797','Coverage','RMS on associated observations','Interpretation'],[
['Original production, Hugging Face elements','1,643','34.3%','164.87 Hz','Published baseline'],['Isolated Space-Track pipeline rerun','2,150','44.8%','137.87 Hz','Different element source and selected candidate set'],['Track-informed initialization','2,627','54.8%','134.90 Hz','Same Space-Track objective; inspected tracks initialize timing'],['Experimental tighter-prior + band correction','2,666','55.6%','134.23 Hz','Hand-selected correction for 69522 / CH1–4, shared by receivers']]))
parts.append(image('01_association_progression.png','All stages use the same 4,797 selected observations. Stage differences include TLE source/candidate selection, initialization, priors and the experimental correction; this is a progression, not a one-factor ablation.'))
parts.append('<p class="sources">Sources: '+ev('comparison')+', '+ev('track_seed_report')+', '+ev('shared_band_timing_result')+'.</p>')
parts.append('''<h2>2. What happened to each original trajectory?</h2><p>The early CH2 set contains 29 coherent descending points selected from 34 originally unassociated points (35 total observations in that interval). The other five unassociated points were excluded as a separate structure. CH4 contains 73 coherent originally unassociated points from 86 total interval observations. Keeping these target definitions fixed prevents unrelated points from obscuring the recovery.</p>''')
parts.append(table(['Target','Candidate','Original → final association','Final all-target RMS','Finding'],[
['RX1 CH2, 50–75 s','69433','0/29 → 29/29 to 69433','116.24 Hz','Timing/association local optimum; coherent trajectory provides a useful start'],['RX1 CH4, 40–100 s','69333','0/73 → 73/73 associated; 72 to 69333','129.88 Hz against 69333','Coherent-track start recovers the long track; one final point chooses another satellite'],['RX1 CH2, 170–190 s','69522','0/27 → 26/27 to 69522','146.11 Hz against 69522','Lower-band trajectory conflicts with shared timing preferred by upper-band observations']]))
parts.append(image('02_target_recovery.png','RMS is computed over every point in each fixed target set, including points the model leaves unassociated. “Associated” and “assigned to the proposed satellite” are different quantities.'))
parts.append('''<p>The unchanged-objective track-seeded fit associated all 73 CH4 points with 69333 at 116.88 Hz RMS and all 29 early CH2 points with 69433 at 117.33 Hz RMS. Their timing parameters were approximately −2.19 s and −2.30 s. The later tighter-prior branch retained the trajectories while changing the CH4 fit slightly. This is why the strongest individual CH4 fit and the final experimental branch have different RMS values.</p>
<h2>3. Root cause established for the first two: optimization and weak timing constraints</h2><p>Before track-informed initialization, the selected Space-Track solution used 69433 and 69333 for scattered observations at unsuitable timing solutions. Coherent-track starts moved these satellites into solutions that explain the long trajectories and lower the same objective: <strong>58,410 → 56,313</strong>, with unpenalized NLL <strong>57,879 → 55,857</strong>. All reported fits passed the saved convergence/replay audit; passing that audit establishes numerical consistency, not satellite identity or geographical accuracy.</p>
<p>The original relative satellite timing prior had a 2 s standard deviation; the common timing prior was 3 s. Accepted total satellite shifts could extend to ±20 s. Simply tightening the prior did not reliably escape the existing timing basin. Compressing initial total shifts to ±3 s, then fitting under the original final bounds, exposed a much more compact timing solution.</p>''')
parts.append(image('03_timing_prior_initialization.png','The 0.5 s prior has a better objective from the compressed start despite fewer associated points than the uncompressed start. Association count alone cannot select a model; objectives with different priors must not be compared directly.'))
parts.append('<p>Under the matched 0.5 s prior, the compressed-start objective is <strong>56,315</strong> versus <strong>59,309</strong> from the original start. Relative timing RMS falls to <strong>1.80 s</strong>, maximum absolute relative timing to <strong>3.31 s</strong>, with 2,633 associations. The same-start 0.5 s branch has 2,764 associations but remains at 5.64 s timing RMS and 17.56 s maximum. These are conditional local refits with the same data, candidate set and 65 s allowance.</p><p class="sources">Sources: '+ev('timing_prior_comparison')+', '+ev('timing_compressed_comparison')+'.</p>')
parts.append('''<h2>4. The late CH2 trajectory: genuine signal support, unresolved physical cause</h2><p>The 27-point seed was extended to 38 points using continuity in the measured trajectory, without satellite predictions. That selection is exploratory. At the tighter-prior baseline, candidate 69522 explains the upper-band observations but the lower trajectory has approximately <strong>+2.74 kHz mean residual</strong>. Moving the satellite's single shared timing parameter improves the lower track while damaging its upper-band support.</p>
<p>A fixed extra orbit-time parameter of <strong>−0.977083 s</strong>, applied only to 69522 in CH1–4, fits the lower trajectory while retaining all 54 selected RX1 upper-band matches in the final comparison. It was learned on the original RX1 seed, then kept fixed for the shared-receiver refit. It is an empirical prediction adjustment; the experiment does not establish a one-second recording-clock error.</p>''')
parts.append(image('04_late_track_explanations.png','A timing-shaped correction predicts the extension and temporal halves more consistently than a constant frequency offset. RF-scale plus offset is competitive on one split but uses an extra parameter and is less stable across the temporal halves.'))
parts.append('''<p>The regional search tested 1,035 Space-Track candidates with ±5 s timing at the fixed tested position. On the extended 38-point lower trajectory, timing-only RMS is <strong>141 Hz for 69522</strong> versus <strong>1,092 Hz for the next candidate</strong>. This is strong evidence within that search, with residual identity/orbit ambiguity still possible.</p>
<p>Allowing a blanket lower-band delay damages hundreds of other associations. With position, calibration and individual satellite timings fixed, an RX1 lower-band −1 s shift reduces that group's associated observations from 877 to 368. The evidence therefore does not support a scanner-wide one-second lower-band delay.</p>
<p class="sources">Sources: ''')
parts.append(ev('late_track_extension')+', '+ev('late_explanation_comparison')+', '+ev('extended_lower_full_search')+', '+ev('rx1_band_time_profile')+'.</p>')
parts.append('''<h2>5. Cross-receiver replay: the discrepancy is present in RX2 too</h2><p>Using the recorded IQ, RX1 frame epochs and calibrated physical CFO branches guided a search in simultaneous RX2 windows. <strong>20 of 38</strong> windows passed margin ≥0.025 and circular CFO difference below 1,000 Hz. Three independent already-associated counterpart controls were recovered 3/3. Physical-frequency branch handling includes three 227,272.727 Hz alias periods; omitting them initially produced misleading non-detections, which were corrected before these reported results.</p>''')
parts.append(image('05_rx2_transfer_controls.png','The RX1-derived correction reduces RMS of the 20 guided RX2 detections from 2,754 Hz to 296 Hz. No correction was fitted to RX2. Guidance, shared calibration and shared position limit independence.'))
parts.append('''<p>Of the 20 RX2 counterparts, 12 lie within 250 Hz and 18 within 500 Hz after correction. Four displaced-epoch controls (137, 503, 997 and 1,499 samples) yielded <strong>0/152</strong> passing detections using the same windows. These are targeted negative controls, not a calibrated global false-alarm probability or a proof of satellite identity.</p>
<p><strong>Why the production candidate list missed them:</strong> none of the 20 counterpart signals had a stored matching candidate within the tested epoch/CFO tolerances. Their physical CFOs span approximately 479–546 kHz, outside the original acquisition half-width of 429.6875 kHz. At the strongest example, widening to ±600 kHz, retaining more candidates, refining the coarse grid or densifying anchors still failed to retain the target. A wider frequency domain alone is insufficient; cross-receiver guidance provides a promising proposal mechanism.</p><p class="sources">Sources: ''')
parts.append(ev('rx2_counterpart_summary')+', '+ev('rx2_timing_transfer')+', '+ev('rx2_guidance_control_summary')+', '+ev('rx2_candidate_retention')+', '+ev('acquisition_counterpart_audit')+', '+ev('acquisition_domain_audit')+', '+ev('acquisition_anchor_audit')+', '+ev('acquisition_coarse_audit')+'.</p>')
parts.append('''<h2>6. Measurement and scaling checks</h2>''')
parts.append(table(['Hypothesis / check','Evidence','Conclusion within tested scope'],[
['Stored CFO peak is biased by kilohertz','Continuous replay of all 38 RX1 probes: median change +53.81 Hz; max absolute change 157.92 Hz; mean orbit residual remains +2,837.72 Hz','Does not explain the discrepancy'],['Probe/sample timing is misbound','All 38 acquisition start counters match the stored probe support; raw chunks are digest verified','No support for the tested binding error'],['RF frequency tag or Doppler scale is wrong','RF-only fit transfers poorly; RF-scale + offset can fit but requires two parameters. Canonical channel-center substitution worsens the centered residual','No supported simple RF-tag repair'],['Within-frame sampling/time-scale mismatch','Three real probes: best warp changes CFO by about +0.05, −4.36 and +2.90 Hz relative to continuous zero-warp replay. Synthetic +2,000 ppm control recovers carrier within 0.5 Hz','Does not explain a kilohertz error in those three probes'],['Frame timing directly proves the orbit','Cross-band frame-phase curvature has related structure, but the late trajectory follows the negative rather than positive geometric-delay curvature under the tested convention','Frame-clock behavior needs its own model; do not treat phase as a validated range observation']]))
parts.append('<p class="sources">Sources: '+ev('raw_cfo_replay_summary')+', '+ev('late_rf_scale_check')+', '+ev('late_within_frame_scale')+', '+ev('within_frame_scale_control')+', '+ev('frame_range_consistency')+'.</p>')
parts.append('''<h2>7. The remaining two point-level exceptions</h2><p>A fixed-fit audit explains the difference between fitting a trajectory and hard-assigning every point. At <strong>172.513 s in late CH2</strong>, candidate 69522 has a +402.98 Hz residual, beyond that point's 377.39 Hz satellite/clutter crossover under the 125 Hz frequency width. Its satellite probability is 0.3455 versus 0.6545 clutter. Exact raw-CFO replay changes the residual only to +402.75 Hz; neighboring target residuals are −59.72 and +5.45 Hz. This remains a local frequency outlier and should not be forced into an association.</p><p>At <strong>70.396 s in CH4</strong>, 69333 fits the point at −20.02 Hz while competitor 100320 fits at +27.47 Hz. The frequency likelihood slightly favors 69333, but the competitor's detection-prior odds are 1.17169 times larger. The final probabilities are 0.4618 for 69333, 0.5350 for 100320 and 0.00325 clutter. Thus all 73 CH4 points are frequency-compatible with 69333, while 72 are hard-assigned to it. This crossing is a pointwise ambiguity that trajectory-level association could address.</p>''')
parts.append(image('three_track_exceptions.png','Point-level audit of the final saved research fit. The late CH2 exception is a frequency outlier; the CH4 exception is a near-tied crossing decided by the detection prior.'))
parts.append('<p class="sources">Source: '+ev('three_track_exception_audit')+'.</p>')
parts.append('''<h2>8. Next debugging goal and model implications</h2><div class="warning"><strong>Proposed investigation goal:</strong> explain and reproducibly recover the three original trajectories without hand-selected satellite exceptions, while preserving the upper-band fits; identify which parts are optimizer failure, acquisition loss, or missing satellite/band signal physics. Qualify the resulting mechanism on excluded observations before considering a production change.</div>
<ol><li><strong>Track-aware initialization:</strong> generate coherent-trajectory proposals before final association, compare several timing starts, and retain the numerical audit. The first two tracks provide direct evidence for this improvement.</li>
<li><strong>Hierarchical satellite/band residual model:</strong> compare a tightly regularized frequency offset, a timing-shaped term and a low-dimensional frequency-evolution term. Learn correction parameters on one trajectory segment, score excluded segments and receivers, and retain a clutter option.</li>
<li><strong>Guided acquisition:</strong> use simultaneous receiver evidence to propose epoch/CFO hypotheses, with explicit physical alias branches and negative controls. Measure candidate recall separately from downstream association.</li>
<li><strong>Physical root cause of 69522:</strong> distinguish band/beam-specific transmitted frequency behavior, orbit inadequacy, and residual identity ambiguity using additional already-recorded tracks and independent element snapshots. A fit parameter must not become a literal clock explanation without timing evidence.</li></ol>
<p>The main unresolved details include the physical origin of the isolated late-CH2 frequency outlier, 69522's lower/upper disagreement, and whether the correction generalizes beyond this selected scan. The CH4 swap now has an identified pointwise prior/likelihood explanation.</p>
<h2>9. Scientific and provenance limits</h2><ul>
<li>All localization comparisons here use fitted RF-dependent calibration coefficient <code>c</code>, as explicitly requested for this investigation. This report does not add a <code>c = 0</code> experiment.</li>
<li>Associated-point RMS compares changing subsets. The target RMS figure keeps each target's full denominator. Neither is a substitute for position error against independent ground truth.</li>
<li>Space-Track and Hugging Face reruns use the same tracking input but different selected satellite sets (59 versus 46). This does not isolate TLE age as the sole cause of the gain.</li>
<li>The late-band correction and target selection were developed after inspecting this scan. Temporal and receiver transfer tests still share full-scan calibration/position; they are not an independent localization evaluation.</li>
<li>The extra 20 RX2 detections are raw-IQ diagnostic evidence and have not been added wholesale to the 4,797-observation shared-fit denominator.</li>
<li>Only existing on-disk data were used. No production code, RF collection or deployment was performed for this report.</li></ul>
<details><summary>Additional diagnostic figures</summary>''')
for name,caption in [('late_track_conflict.png','The original lower/upper timing conflict for 69522.'),('raw_cfo_replay.png','Continuous raw-IQ CFO replay of the extended lower trajectory.'),('rx1_band_time_profile.png','Conditional blanket lower-band orbit-time profiles for each receiver.'),('frame_phase_crossband.png','Cross-band frame phases after separate phase constants are removed; offsets are not compared directly.'),('frame_range_consistency.png','Exploratory detrended frame-phase versus positive/negative geometric delay. This is not a validated range estimator.')]:parts.append(image(name,caption))
parts.append('</details><h3>Evidence bundle</h3><p>The adjacent <a href="manifest.json">manifest</a> records hashes for copied JSON evidence, figures and reproduction scripts. The scripts preserve the original diagnostic context and may reference the deployment/input locations; this bundle is a durable evidence snapshot, not a self-contained raw-IQ replay dataset. '+ev('comparison_manifest','Input and Space-Track snapshot identifiers')+' are retained. The standalone HTML embeds its figures and can be opened without a server.</p><footer>Prepared from saved evidence on '+datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')+'. Report artifacts only; no production changes.</footer></main></body></html>')
(DEST/'report.html').write_text(''.join(parts))
manifest=dict(scan='fast8-auto-20261016-161535-99008d35-1-lower',run='fast-9571943d3dccdf4f327e1346d1bf34b8',source_evidence_root=str(SOURCE),created_utc=datetime.now(timezone.utc).isoformat(),scope='Saved-evidence reporting only; no production change or new fit',files=[])
for path in sorted(DEST.rglob('*')):
    if path.is_file() and path.name!='manifest.json':manifest['files'].append(dict(path=str(path.relative_to(DEST)),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(report=str(DEST/'report.html'),files=len(manifest['files']),figure_count=len(list((DEST/'figures').glob('*.png'))),bytes=(DEST/'report.html').stat().st_size),indent=2))
