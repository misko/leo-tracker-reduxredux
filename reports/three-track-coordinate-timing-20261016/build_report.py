"""Package executed timing-coordinate fits and their held classifier results."""
import hashlib,json,shutil
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

HERE=Path(__file__).resolve().parent;RESULTS=HERE/'results';RESULTS.mkdir(exist_ok=True)
SOURCE=Path('/tmp/three-track-coordinate-timing');folds=['early_to_late','late_to_early']
summary=[];rows={}
for fold in folds:
    for arm in ['fitted-c','zero-c']:
        folder=fold+'_'+arm+'_v1';source=SOURCE/folder
        shutil.copytree(source,RESULTS/folder,dirs_exist_ok=True)
        d=json.loads((source/'result.json').read_text());rows[(fold,arm)]=d
        summary.append(dict(fold=fold,arm=arm,profile=d['profile'],audit=d['audit'],
            tracks=d['pipeline_classification']['tracks'],fit_elapsed_seconds=d['fit_elapsed_seconds']))
for p in SOURCE.glob('verify-*.json'):shutil.copy2(p,RESULTS/p.name)
fig=Figure(figsize=(11,4.4),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for ax,fold in zip(axes,folds):
    for offset,arm,color in [(-.18,'fitted-c','#167f9b'),(.18,'zero-c','#dc7824')]:
        d=rows[(fold,arm)];profile=d['profile']
        gains=[profile['start_objective']-profile['end_objective'],
               profile['start_objective']-d['audit']['objective']]
        bars=ax.bar(np.arange(2)+offset,gains,.36,color=color,label=arm)
        for bar,gain in zip(bars,gains):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+35,str(round(gain)),ha='center',fontsize=8)
    ax.set(xticks=np.arange(2),xticklabels=['After timing sweep','After joint refit'],
           ylabel='Decrease in original training objective',title='Forward fold' if fold==folds[0] else 'Reverse fold')
    ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
fig.suptitle('A stationary cold endpoint can still contain much worse timing basins\n'
             'Same normalized point likelihood and priors; each RF arm measured against its own starting value')
fig.savefig(HERE/'01_training_objective.png',dpi=180)

fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for ax,fold in zip(axes,folds):
    baseline_path=HERE.parent/'three-track-local-segments-20261016/results'/f'evaluation-{fold}-v6/evaluation.json'
    baseline=json.loads(baseline_path.read_text())['cold_pipeline_classification']['tracks']
    series=[(-.25,baseline,'#999999','Before timing sweep'),
            (0.,rows[(fold,'fitted-c')]['pipeline_classification']['tracks'],'#167f9b','After · fitted c'),
            (.25,rows[(fold,'zero-c')]['pipeline_classification']['tracks'],'#dc7824','After · c = 0')]
    for offset,tracks,color,label in series:
        bars=ax.bar(np.arange(3)+offset,[t['test_matches_training_satellite']/t['test_count'] for t in tracks],.25,color=color,label=label)
        for bar,t in zip(bars,tracks):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.025,
            f"{t['test_matches_training_satellite']}/{t['test_count']}",ha='center',fontsize=7)
    ax.set(xticks=np.arange(3),xticklabels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s'],
        ylim=(0,1.2),ylabel='Fraction of all held trajectory points',title='Forward fold' if fold==folds[0] else 'Reverse fold')
    ax.legend(fontsize=7);ax.grid(axis='y',alpha=.2)
fig.suptitle('Timing basin search restores some coherent predictions, but not all three trajectories\n'
    'Actual frozen classifier; training-selected labels; missing estimates stay in the denominator')
fig.savefig(HERE/'02_held_coherence.png',dpi=180)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
files=[dict(path=str(p.relative_to(HERE)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
       for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts]
(HERE/'manifest.json').write_text(json.dumps(dict(scope='Training-only optimizer research and held classifier tests. '
    'No independently verified identity labels or geographic accuracy.',files=files),indent=2)+'\n')
print(json.dumps(dict(files=len(files),results=[dict(fold=r['fold'],arm=r['arm'],audit=r['audit'],
    matched=sum(t['test_matches_training_satellite'] for t in r['tracks']),held=sum(t['test_count'] for t in r['tracks'])) for r in summary])))
