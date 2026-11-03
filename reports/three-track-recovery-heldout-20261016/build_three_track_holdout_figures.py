from pathlib import Path
import json,shutil,hashlib
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

source=Path('/tmp/three-track-investigation/space-track-pipeline-rerun')
dest=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/three-track-recovery-heldout-20261016');dest.mkdir(exist_ok=True)
data=json.loads((source/'generic_recovery_target_excluded_controls.json').read_text())
old=json.loads((source/'train_only_candidate_temporal_transfer.json').read_text())
emission=json.loads((source/'emission_model_target_excluded_transfer.json').read_text())
colors=['#197f9b','#e27826','#7251a0'];names=['early_ch2','ch4','late_ch2'];labels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s']
fig=Figure(figsize=(13,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,3)
for ax,name,label in zip(axes,names,labels):
    real=[r['records'][0] for r in data['results'] if r['track']==name]
    before=[r['ranked'][0]['test_rms_hz'] for r in old['results'] if r['track']==name]
    x=np.arange(2)
    ax.bar(x-.18,before,.36,color='#aaaaaa',label='Original full-scan calibration')
    bars=ax.bar(x+.18,[r['test_rms_hz'] for r in real],.36,color=colors[names.index(name)],label='Target-excluded calibration')
    for b,r in zip(bars,real):ax.text(b.get_x()+b.get_width()/2,b.get_height()+9,f"{r['test_rms_hz']:.0f}",ha='center')
    ax.set(title=label,xticks=x,xticklabels=['Early → late','Late → early'],ylabel='Withheld frequency RMS (Hz)',ylim=(0,560));ax.grid(axis='y',alpha=.2)
axes[0].legend(fontsize=8)
fig.suptitle('Generic training-only satellite/timing search across 1,035 candidates\n129 target measurements excluded from the new calibration fit; retained full-scan conditioning is documented')
fig.savefig(dest/'01_temporal_transfer.png',dpi=180)

fig=Figure(figsize=(13,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,3);all_residuals=[]
for ax,name,label,color in zip(axes,names,labels,colors):
    rr=np.concatenate([r['records'][0]['test_residuals_hz'] for r in data['results'] if r['track']==name]);all_residuals.extend(rr.tolist())
    ax.hist(rr,bins=np.arange(-500,551,50),color=color,edgecolor='white');ax.axvline(-375,color='gray',ls='--');ax.axvline(375,color='gray',ls='--')
    ax.set(title=f'{label} · n={len(rr)}',xlabel='Withheld frequency residual (Hz)',ylabel='Point count');ax.grid(axis='y',alpha=.2)
fig.suptitle('Each original target point evaluated once using the opposite temporal half\nDashed lines ±375 Hz are a diagnostic tolerance, not posterior association or position accuracy')
fig.savefig(dest/'02_withheld_residual_histograms.png',dpi=180)

fig=Figure(figsize=(13,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for i,(name,label,color) in enumerate(zip(names,labels,colors)):
    real=[];null=[]
    for r in data['results']:
        if r['track']!=name:continue
        real.append(r['records'][0]['training_rms_hz']);null.extend(x['training_rms_hz'] for x in r['records'][1:])
    axes[0].scatter(np.full(len(null),i)+np.linspace(-.18,.18,len(null)),null,color=color,alpha=.5,s=22)
    axes[0].scatter(np.full(len(real),i),real,marker='*',s=160,color=color,edgecolor='black',zorder=4)
axes[0].axhline(375,color='gray',ls='--');axes[0].set(yscale='log',xticks=range(3),xticklabels=labels,ylabel='Best training RMS across candidates (Hz)',title='6 real cases pass; 0/48 shuffled cases pass')
modes=['frequency_offset','frequency_affine','doppler_derivative_bias','timing'];x=np.arange(4)
for j,(split,caption) in enumerate([('early_to_late','Early → late'),('late_to_early','Late → early')]):
    rows=[next(r for r in emission['results'] if r['track']=='late_ch2' and r['split']==split and r['mode']==mode) for mode in modes]
    bars=axes[1].bar(x+(j-.5)*.36,[r['test_rms_hz'] for r in rows],.36,label=caption,color=colors[j])
    for b,r in zip(bars,rows):axes[1].text(b.get_x()+b.get_width()/2,b.get_height()+5,f"{r['test_rms_hz']:.0f}",ha='center',fontsize=8)
axes[1].set(xticks=x,xticklabels=['Offset\n1 parameter','Offset + drift\n2 parameters','Doppler derivative\n1 parameter','Orbit-time shift\n1 parameter'],ylabel='Late CH2 withheld RMS (Hz)',ylim=(0,470),title='Frequency basis can predict the timing-shaped discrepancy');axes[1].legend(fontsize=8)
for ax in axes:ax.grid(axis='y',alpha=.2)
fig.suptitle('Negative controls and competing residual models\nShuffling is an exploratory control; the derivative coefficient does not assert a clock error')
fig.savefig(dest/'03_controls_and_residual_models.png',dpi=180)

for name in ['train_only_candidate_temporal_transfer.json','excluded_calibration_fitted-c.json','excluded_calibration_zero-c.json','excluded_calibration_fitted-c_from_zero.json','excluded_calibration_cv_fitted-c.json','excluded_calibration_cv_zero-c.json','generic_recovery_target_excluded_controls.json','emission_model_target_excluded_transfer.json']:
    shutil.copy2(source/name,dest/name)
for name in ['three_track_train_only_candidate_search.py','three_track_excluded_calibration_fit.py','three_track_excluded_calibration_from_zero.py','three_track_excluded_calibration_cv.py','three_track_generic_recovery_controls.py','three_track_emission_model_transfer.py','build_three_track_holdout_figures.py','compare_space_track_pipeline.py']:
    shutil.copy2(Path('/tmp')/name,dest/name)
summary=dict(points=len(all_residuals),within_375hz=int(np.sum(abs(np.array(all_residuals))<=375)),rms_hz=float(np.sqrt(np.mean(np.array(all_residuals)**2))),real_gate_passes=sum(r['records'][0]['passes_predeclared_gate'] for r in data['results']),shuffled_gate_passes=sum(c['passes_predeclared_gate'] for r in data['results'] for c in r['records'][1:]),shuffled_cases=48)
(dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
