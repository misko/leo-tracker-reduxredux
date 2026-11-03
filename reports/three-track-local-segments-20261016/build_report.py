"""Package completed local-segment diagnostics and draw measured coverage."""
import hashlib,json,shutil
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

HERE=Path(__file__).resolve().parent
SOURCE=Path('/tmp/three-track-local-segments');RESULTS=HERE/'results';RESULTS.mkdir(exist_ok=True)
folds=['early_to_late','late_to_early'];audit=[]
for fold in folds:
    old=json.loads((SOURCE/(fold+'-v1')/'audit.json').read_text())
    current=json.loads((SOURCE/(fold+'-v4-audit.json')).read_text())
    for suffix in ['v2-generation','v3-audit','v4-audit']:
        shutil.copy2(SOURCE/(fold+'-'+suffix+'.json'),RESULTS/(fold+'-'+suffix+'.json'))
    shutil.copy2(SOURCE/(fold+'-v1')/'audit.json',RESULTS/(fold+'-v1-audit.json'))
    audit.append(dict(fold=fold,old=old,current=current))
for p in SOURCE.glob('*pilot*.json'):shutil.copy2(p,RESULTS/p.name)
for folder in ['baseline-evaluator-qualification','baseline-classifier-final','baseline-classifier-forward',
               'reverse-merge-seed-pilot-v1','reverse-timing-conflicts-v1','reverse-timing-conflicts-v2']:
    if (SOURCE/folder).exists():shutil.copytree(SOURCE/folder,RESULTS/folder,dirs_exist_ok=True)
attempts=[]
for version in ['v4','v5','v6']:
    for fold in folds:
        source=SOURCE/f'cold-{fold}-{version}'
        terminal=source/'output/terminal.json'
        if not terminal.exists():
            attempts.append(dict(version=version,fold=fold,state='not_packaged_no_terminal'))
            continue
        destination=RESULTS/f'cold-{fold}-{version}'
        destination.mkdir(exist_ok=True)
        for name in ['derivation.json','preparation-receipt.json','bootstrap-replacement-receipt.json','automatic-segments.json']:
            shutil.copy2(source/name,destination/name)
        shutil.copytree(source/'output',destination/'output',dirs_exist_ok=True)
        d=json.loads(terminal.read_text());points=[json.loads(p.read_text()) for p in (source/'output/stages').glob('discovery-point:*.json')]
        attempts.append(dict(version=version,fold=fold,state=d['state'],reason=d.get('reason'),
            elapsed_seconds=d['elapsed_seconds'],discovery_points=len(points),
            accepted_all_points=sum(p['fits'].get('all',{}).get('converged',False) for p in points),
            terminal_sha256=hashlib.sha256(terminal.read_bytes()).hexdigest()))
for source in SOURCE.glob('evaluation-*/evaluation.json'):
    shutil.copytree(source.parent,RESULTS/source.parent.name,dirs_exist_ok=True)

evaluations={fold:RESULTS/f'evaluation-{fold}-v6/evaluation.json' for fold in folds}
if all(p.exists() for p in evaluations.values()):
    fig=Figure(figsize=(11,4.3),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
    summary=[]
    for ax,fold in zip(axes,folds):
        baseline='baseline-classifier-forward' if fold=='early_to_late' else 'baseline-classifier-final'
        old=json.loads((RESULTS/baseline/'evaluation.json').read_text())['cold_pipeline_classification']
        new=json.loads(evaluations[fold].read_text())['cold_pipeline_classification']
        for offset,d,color,label in [(-.18,old,'#8d8d8d','Original cold pipeline'),
                                     (.18,new,'#167f9b','Local-segment cold pipeline')]:
            fractions=[t['test_matches_training_satellite']/t['test_count'] for t in d['tracks']]
            bars=ax.bar(np.arange(3)+offset,fractions,.36,color=color,label=label)
            for bar,t in zip(bars,d['tracks']):
                ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.035,
                    f"{t['test_matches_training_satellite']}/{t['test_count']}",ha='center',fontsize=8)
        ax.set(xticks=np.arange(3),xticklabels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s'],
               ylim=(0,1.30),ylabel='Fraction of all held trajectory points',
               title='Forward fold' if fold=='early_to_late' else 'Reverse fold')
        ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
        summary.append(dict(fold=fold,before=old,after=new))
    fig.suptitle('Automatic short-segment bootstrap does not improve coherent pipeline recovery\n'
        'Held points must match the training-selected candidate; missing groups remain in the denominator')
    fig.savefig(HERE/'03_actual_pipeline_coherence.png',dpi=180)
    (HERE/'pipeline_comparison.json').write_text(json.dumps(summary,indent=2)+'\n')

    fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
    for ax,fold in zip(axes,folds):
        capsule=HERE.parent/'three-track-recovery-replay-20261016/checkpoints'/fold
        old=json.loads((capsule/'cold_candidate_temporal_transfer.json').read_text())
        new=json.loads((RESULTS/f'evaluation-{fold}-v6/fitted-c.json').read_text())
        old_tracks=[next(r for r in old['results'] if r['track']==name)['ranked'][0]
                    for name in ['early_ch2','ch4','late_ch2']]
        for offset,tracks,color,label in [(-.18,old_tracks,'#8d8d8d','Original calibration'),
                                         (.18,new['tracks'],'#167f9b','Local-segment calibration')]:
            bars=ax.bar(np.arange(3)+offset,[t['test_rms_hz'] for t in tracks],.36,color=color,label=label)
            for bar,t in zip(bars,tracks):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()*1.06,
                                               str(round(t['test_rms_hz'])),ha='center',fontsize=8)
        ax.axhline(375,color='gray',ls=':',lw=.8)
        ax.set(xticks=np.arange(3),xticklabels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s'],
               yscale='log',ylim=(70,4000),ylabel='Withheld carrier RMS (Hz)',
               title='Forward fold' if fold=='early_to_late' else 'Reverse fold')
        ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Diagnostic candidate/timing searches are different from actual pipeline recovery\n'
        'Full regional candidate bank; identity and timing selected from target training halves only; fitted c')
    fig.savefig(HERE/'04_diagnostic_temporal_rms.png',dpi=180)

# Compare only points completed in both attempts with the same candidate bank.
fig=Figure(figsize=(11,4.3),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
numerical_comparison=[]
for ax,fold in zip(axes,folds):
    paths={version:{p.stem:p for p in (SOURCE/f'cold-{fold}-{version}'/'output/stages').glob('discovery-point:*.json')}
           for version in ['v4','v5']}
    rows=[]
    for key in sorted(set(paths['v4'])&set(paths['v5'])):
        old=json.loads(paths['v4'][key].read_text());new=json.loads(paths['v5'][key].read_text())
        if old['catalogue_numbers']!=new['catalogue_numbers']:continue
        if not all('all' in d['fits'] for d in [old,new]):continue
        rows.append(dict(point=key,candidates=len(old['catalogue_numbers']),
            before=old['fits']['all']['stationarity'],after=new['fits']['all']['stationarity'],
            before_converged=old['fits']['all']['converged'],after_converged=new['fits']['all']['converged']))
    numerical_comparison.append(dict(fold=fold,points=rows))
    if rows:
        ax.plot(np.arange(1,len(rows)+1),[r['before'] for r in rows],'x-',color='#c17729',label='5 s / 200 iterations')
        ax.plot(np.arange(1,len(rows)+1),[r['after'] for r in rows],'o-',color='#167f9b',label='15 s / 600 iterations')
    ax.axhline(.001,color='gray',ls=':',label='Unchanged strict stationarity gate')
    ax.set(yscale='log',xlabel='Completed common discovery point (ordered by key)',ylabel='Projected stationarity',
           title='Forward fold' if fold==folds[0] else 'Reverse fold')
    ax.legend(fontsize=8);ax.grid(alpha=.2)
fig.suptitle('Additional combined-fit optimization resolves numerical discovery failures\n'
             'Same observations and candidate banks at each compared point; no held accuracy claim')
fig.savefig(HERE/'02_discovery_numerical_gate.png',dpi=180)
(HERE/'discovery_numerical_comparison.json').write_text(json.dumps(numerical_comparison,indent=2)+'\n')

fig=Figure(figsize=(11,4.3),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
labels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s'];x=np.arange(3)
for ax,row in zip(axes,audit):
    old=row['old']['target_coverage'];new=row['current']['target_coverage']
    for offset,key,color,label in [(-.24,'old','#9b9b9b','Original bootstrap'),
                                    (0.,'proposals','#94cbb2','Local proposals'),
                                    (.24,'selected','#147e9c','Selected local segments')]:
        values=[t['original_bootstrap']['covered'] for t in old] if key=='old' else [t[key] for t in new]
        bars=ax.bar(x+offset,values,.24,color=color,label=label)
        for bar,value in zip(bars,values):ax.text(bar.get_x()+bar.get_width()/2,value+.45,str(value),ha='center',fontsize=8)
    ax.plot(x,[t['training_count'] for t in new],'k_',ms=45,label='Available training points')
    ax.set(xticks=x,xticklabels=labels,ylim=(0,50),ylabel='Original target training points represented',
           title='Forward fold' if row['fold']==folds[0] else 'Reverse fold')
    ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
fig.suptitle('Orbit-blind extraction recovers previously missing training segments\n'
             'Coverage is measured after extraction; it is not satellite or position accuracy')
fig.savefig(HERE/'01_training_track_coverage.png',dpi=180)
(HERE/'attempt_summary.json').write_text(json.dumps(attempts,indent=2)+'\n')
files=[dict(path=str(p.relative_to(HERE)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
       for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts]
(HERE/'manifest.json').write_text(json.dumps(dict(scope='Local research and bounded existing-corpus replays. '
    'No production changes. Development membership-coverage diagnostics are not held-out satellite identification.',files=files),indent=2)+'\n')
print(json.dumps(dict(files=len(files),attempts=attempts)))
