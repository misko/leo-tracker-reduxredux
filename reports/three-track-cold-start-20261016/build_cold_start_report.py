from pathlib import Path
import json,shutil,hashlib
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

base=Path('/tmp/three-track-investigation');dest=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/three-track-cold-start-20261016')
folds=['early_to_late','late_to_early'];names=['early_ch2','ch4','late_ch2'];labels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s']
fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2);x=np.arange(3)
for j,fold in enumerate(folds):
    for method,color,offset in [('v1','#167f9b',-.25),('union-v2','#dc7824',0),('hints-v3','#8b5aa5',.25)]:
        folder=base/('cold-fold-'+fold+'-'+method);data=json.loads((folder/'cold_candidate_temporal_transfer.json').read_text());rows=[next(r['ranked'][0] for r in data['results'] if r['track']==name) for name in names]
        bars=axes[j].bar(x+offset,[r['test_rms_hz'] for r in rows],.25,color=color,label={'v1':'Original retention','union-v2':'Union retention','hints-v3':'Supplied training groups'}[method])
        for b,r in zip(bars,rows):axes[j].text(b.get_x()+b.get_width()/2,b.get_height()*1.08,f"{r['test_rms_hz']:.0f}",ha='center',fontsize=8)
    axes[j].set(xticks=x,xticklabels=labels,yscale='log',ylim=(70,12000),ylabel='Withheld frequency RMS (Hz)',title='Early → late' if j==0 else 'Late → early');axes[j].grid(axis='y',alpha=.2);axes[j].legend(fontsize=8)
fig.suptitle('Fresh discovery and calibration on declared training inputs\nRetaining or supplying coherent tracks alone does not repair source selection')
fig.savefig(dest/'01_cold_temporal_transfer.png',dpi=180)

audit=json.loads((base/'training_track_discovery_audit.json').read_text());fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for j,fold in enumerate(folds):
    rows=[next(r for r in audit if r['fold']==fold and r['track']==name) for name in names]
    for view,color,offset in [('low','#dc7824',-.18),('all','#167f9b',.18)]:
        values=[next(v['points_in_any_bootstrap_track'] for v in r['views'] if v['view']==view) for r in rows]
        bars=axes[j].bar(x+offset,values,.36,color=color,label='CH1–4 bootstrap' if view=='low' else 'CH1–8 bootstrap')
        for b,val in zip(bars,values):axes[j].text(b.get_x()+b.get_width()/2,val+.5,str(val),ha='center')
    axes[j].set(xticks=x,xticklabels=labels,ylim=(0,44),ylabel='Target training points retained',title='Early-half training' if j==0 else 'Late-half training');axes[j].legend(fontsize=8);axes[j].grid(axis='y',alpha=.2)
fig.suptitle('Observed loss of target track evidence before source generation\nThe reverse CH4 track ranks 20th by span; the combined view retains 12 tracks per receiver')
fig.savefig(dest/'02_bootstrap_target_coverage.png',dpi=180)

trials=[json.loads(p.read_text()) for p in (base/'cold-fold-late_to_early-v1').glob('coherent_receiver_search_point_*.json')]
if trials:
    selected=min(trials,key=lambda r:r['training_objective'])
    fig=Figure(figsize=(7,5),layout='constrained');FigureCanvasAgg(fig);ax=fig.subplots()
    for index,(name,label,color) in enumerate(zip(names,labels,['#167f9b','#dc7824','#8b5aa5'])):
        rows=[next(t for t in trial['tracks'] if t['track']==name) for trial in trials]
        ax.scatter([r['training_rms_hz'] for r in rows],[r['test_rms_hz'] for r in rows],label=label,color=color,alpha=.7)
        best=next(t for t in selected['tracks'] if t['track']==name)
        ax.scatter([best['training_rms_hz']],[best['test_rms_hz']],s=150,facecolors='none',edgecolors='black',linewidths=1.3)
    ax.plot([70,7000],[70,7000],':',color='gray',label='Equal training and withheld RMS')
    ax.axvline(375,color='gray',alpha=.5);ax.set(xscale='log',yscale='log',xlabel='Training frequency RMS (Hz)',ylabel='Withheld frequency RMS (Hz)',title='Good short-track training fit can fail temporal transfer\nNine regional points; black rings: point chosen by training objective only')
    ax.grid(alpha=.2);ax.legend(fontsize=8);fig.savefig(dest/'03_coherent_training_vs_test.png',dpi=180)

folder=base/'cold-fold-late_to_early-v1'
variants=[('fixed','fitted-c','Frozen · fitted c','#167f9b'),('free','fitted-c','Free · fitted c','#dc7824'),('fixed','zero-c','Frozen · c = 0','#8b5aa5')]
if all((folder/f'refine_band_contrast_{v}_{a}_pass2_temporal_transfer.json').exists() for v,a,_,_ in variants):
    fig=Figure(figsize=(9,4.5),layout='constrained');FigureCanvasAgg(fig);ax=fig.subplots()
    for offset,(variant,arm,label,color) in zip([-.25,0,.25],variants):
        data=json.loads((folder/f'refine_band_contrast_{variant}_{arm}_pass2_temporal_transfer.json').read_text())
        rows=[next(r['ranked'][0] for r in data['results'] if r['track']==name) for name in names]
        bars=ax.bar(x+offset,[r['test_rms_hz'] for r in rows],.25,label=label,color=color)
        for bar,row in zip(bars,rows):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()*1.06,str(round(row['test_rms_hz'])),ha='center',fontsize=8)
    ax.set(xticks=x,xticklabels=labels,yscale='log',ylim=(80,3500),ylabel='Withheld carrier RMS (Hz)',title='Freeing band offsets does not recover all three reverse-fold tracks\nCandidates can differ between models; these are frequency errors, not position errors')
    ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8);fig.savefig(dest/'04_band_contrast_controls.png',dpi=180)

for fold in folds:
    for method in ['v1','union-v2']:
        folder=base/('cold-fold-'+fold+'-'+method);prefix=fold+'_'+method+'_'
        for name in ['derivation.json','cold_context_transport.json','cold_candidate_temporal_transfer.json']:
            shutil.copy2(folder/name,dest/(prefix+name))
        shutil.copy2(folder/'output/terminal.json',dest/(prefix+'terminal.json'))
        for name in ['bootstrap_retention_receipt.json','generic_joint_early_to_late_fitted-c.json','generic_joint_early_to_late_fitted-c_no_bias.json','generic_joint_early_to_late_fitted-c_no_bias_from_band.json','cold_forward_rx2_transfer.json','cold_forward_flagged_background_points.json','cold_candidate_temporal_transfer_source_A-4.json']:
            if (folder/name).exists():shutil.copy2(folder/name,dest/(prefix+name))
    hints=base/('cold-fold-'+fold+'-hints-v3')
    for name in ['derivation.json','bootstrap_track_hints_receipt.json','cold_context_transport.json','cold_candidate_temporal_transfer.json']:
        if (hints/name).exists():shutil.copy2(hints/name,dest/(fold+'_hints_v3_'+name))
    if (hints/'output/terminal.json').exists():shutil.copy2(hints/'output/terminal.json',dest/(fold+'_hints_v3_terminal.json'))
for name in ['training_track_discovery_audit.json']:
    shutil.copy2(base/name,dest/name)
for folder in [base/('cold-fold-'+fold+'-v1') for fold in folds]:
    for pattern in ['alternate_B_*_shared.json','alternate_B_*_transport.json','alternate_B_*_temporal_transfer.json','coherent_receiver_search*.json','refine_band_contrast*.json','discovery_low_rank*.json']:
        for path in folder.glob(pattern):shutil.copy2(path,dest/(folder.name+'_'+path.name))
for name in ['three_track_alternate_donor_fit.py','three_track_alternate_donor_context.py','three_track_alternate_donor_cv.py','three_track_coherent_receiver_search.py','three_track_refine_band_contrast.py','three_track_refined_band_context.py','three_track_refined_band_cv.py','three_track_discovery_low_context.py','three_track_discovery_low_cv.py']:
    shutil.copy2(Path('/tmp')/name,dest/name)
for name in ['original_full_B_continuation.json','joint_background_stability.json']:
    shutil.copy2(base/'space-track-pipeline-rerun'/name,dest/name)
for name in ['launch_cold_track_fold.py','launch_cold_fold_union_bootstrap.py','launch_cold_fold_track_hints.py','three_track_cold_context.py','three_track_cold_candidate_cv.py','three_track_train_only_candidate_search.py','frozen_band_bias_joint.py','run_generic_joint_track_fold.py','continue_original_full_B_fit.py','audit_training_track_discovery.py','audit_joint_background_stability.py','cold_forward_rx2_transfer.py','build_cold_start_report.py']:
    shutil.copy2(Path('/tmp')/name,dest/name)
files=[dict(path=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(dest.iterdir()) if p.is_file() and p.name!='manifest.json']
(dest/'manifest.json').write_text(json.dumps(dict(recording='fast8-auto-20261016-161535-99008d35-1-lower',scope='Cold-fold validation; union retention and supplied training-track groups both fail to repair cold source selection.',files=files),indent=2)+'\n');print(json.dumps(dict(directory=str(dest),artifacts=len(files))))
