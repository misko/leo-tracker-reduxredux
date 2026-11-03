from pathlib import Path
import json,shutil,hashlib
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

source=Path('/tmp/three-track-investigation/space-track-pipeline-rerun');dest=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/three-track-joint-heldout-20261016')
folds=['early_to_late','late_to_early'];arms=['fitted-c','zero-c'];variants=['band_bias','no_bias'];data={}
for fold in folds:
    for arm in arms:
        for variant in variants:
            name=f'generic_joint_{fold}_{arm}'+('_no_bias' if variant=='no_bias' else '')+'_pass2.json'
            d=json.loads((source/name).read_text());assert d['audit']['accepted'];data[fold,arm,variant]=d
            assert d['held_measurement_invariance_error']==0
fig=Figure(figsize=(13,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,3)
for i,(ax,name,label) in enumerate(zip(axes,['early_ch2','ch4','late_ch2'],['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s'])):
    for variant,color,style,label2 in [('no_bias','#777777','--','No band term'),('band_bias','#167f9b','-','Learned band term')]:
        rr=np.concatenate([next(r for r in data[f,'fitted-c',variant]['after']['tracks'] if r['track']==name)['test_residuals_hz'] for f in folds]);x=np.sort(abs(rr));ax.step(np.r_[.1,x],np.r_[0,np.arange(1,len(x)+1)/len(x)],where='post',label=label2,color=color,ls=style,lw=2)
    ax.axvline(375,color='gray',ls=':',lw=1);ax.set(xscale='log',xlim=(.1,10000),ylim=(0,1.03),title=label,xlabel='Absolute withheld frequency residual (Hz)',ylabel='Fraction of all target points');ax.grid(alpha=.2)
axes[0].legend(fontsize=8);fig.suptitle('Joint fit: same target points, declared temporal folds, fitted c\nFrequency prediction and association evidence; no geographical accuracy claim')
fig.savefig(dest/'01_joint_frequency_cdfs.png',dpi=180)

fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2);x=np.arange(2)
for j,(variant,color,label) in enumerate([('no_bias','#888888','No band term'),('band_bias','#167f9b','Learned band term')]):
    values=[data[f,'fitted-c',variant]['after']['all_associated'] for f in folds];bars=axes[0].bar(x+(j-.5)*.36,values,.36,label=label,color=color)
    for b,val in zip(bars,values):axes[0].text(b.get_x()+b.get_width()/2,val+12,str(val),ha='center')
axes[0].set(xticks=x,xticklabels=['Early → late','Late → early'],ylim=(0,3000),ylabel='Associated / 4,797 observations',title='Whole-scan classification; training and test mixed');axes[0].legend(fontsize=8)
for j,(arm,color,label) in enumerate([('fitted-c','#167f9b','Fitted c'),('zero-c','#da7a22','c = 0')]):
    rows=[data[f,arm,'band_bias']['after'] for f in folds];bars=axes[1].bar(x+(j-.5)*.36,[r['withheld_nll'] for r in rows],.36,label=label,color=color)
    for b,r in zip(bars,rows):axes[1].text(b.get_x()+b.get_width()/2,b.get_height()+5,f"{r['withheld_nll']:.1f}",ha='center',fontsize=9)
axes[1].set(xticks=x,xticklabels=['Early → late','Late → early'],ylim=(0,750),ylabel='Withheld conditional NLL',title='Calibration ablation with the band term');axes[1].legend(fontsize=8)
for ax in axes:ax.grid(axis='y',alpha=.2)
fig.suptitle('Matched joint-model comparisons; all endpoints numerically accepted\nBetter training fit does not establish improved held-out localization')
fig.savefig(dest/'02_joint_coverage_and_controls.png',dpi=180)

for p in source.glob('generic_joint*.json'):shutil.copy2(p,dest/p.name)
for name in ['joint_common_shift_derivative_step_sweep.json','excluded_calibration_fitted-c_from_zero.json','generic_recovery_target_excluded_controls.json']:
    shutil.copy2(source/name,dest/name)
for name in ['frozen_band_bias_joint.py','run_generic_joint_track_fold.py','launch_cold_target_excluded.py','launch_cold_track_fold.py','three_track_cold_context.py','three_track_cold_candidate_cv.py','build_joint_track_report.py']:
    shutil.copy2(Path('/tmp')/name,dest/name)
cold=Path('/tmp/three-track-investigation/cold-target-excluded-v1')
for name in ['derivation.json','cold_context_transport.json','cold_candidate_temporal_transfer.json']:
    shutil.copy2(cold/name,dest/('cold_background_'+name))
shutil.copy2(cold/'output/terminal.json',dest/'cold_background_terminal.json')
summary={}
for arm in arms:
    with_bias=[data[f,arm,'band_bias'] for f in folds];without=[data[f,arm,'no_bias'] for f in folds]
    summary[arm]=dict(with_band=[d['after'] for d in with_bias],without_band=[d['after'] for d in without],all_joint_audits_accepted=all(d['audit']['accepted'] for d in with_bias+without))
(dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
items=[dict(path=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(dest.iterdir()) if p.is_file() and p.name!='manifest.json']
(dest/'manifest.json').write_text(json.dumps(dict(recording='fast8-auto-20261016-161535-99008d35-1-lower',scope='Conditional joint-model test plus cold background-only failure diagnostic; fresh training-fold controls pending.',files=items),indent=2)+'\n')
print(json.dumps(dict(directory=str(dest),artifacts=len(items))))
