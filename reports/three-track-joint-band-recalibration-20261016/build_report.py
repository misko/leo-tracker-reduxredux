"""Package matched band-calibration controls and held classifier figures."""
import hashlib,json,shutil
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

HERE=Path(__file__).resolve().parent;RESULTS=HERE/'results';RESULTS.mkdir(exist_ok=True)
SOURCE=Path('/tmp/three-track-joint-band-recalibration');folds=['early_to_late','late_to_early'];rows={}
for fold in folds:
    for arm in ['fitted-c','zero-c']:
        folder=fold+'_'+arm+'_v1';shutil.copytree(SOURCE/folder,RESULTS/folder,dirs_exist_ok=True)
        rows[(fold,arm)]=json.loads((RESULTS/folder/'result.json').read_text())
for path in SOURCE.glob('verify-*.json'):shutil.copy2(path,RESULTS/path.name)
fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for ax,fold in zip(axes,folds):
    for offset,variant,color,label in [(-.18,'frozen','#999999','Frozen contrast'),(.18,'joint','#167f9b','Refitted contrast')]:
        result=rows[(fold,'fitted-c')];row=next(r for r in result['variants'] if r['variant']==variant)
        tracks=row['pipeline_classification']['tracks'];accepted=row['audit']['accepted']
        bars=ax.bar(np.arange(3)+offset,[t['test_matches_training_satellite']/t['test_count'] for t in tracks],.36,
            color=color,alpha=1 if accepted else .5,hatch=None if accepted else '//',label=label)
        for bar,t in zip(bars,tracks):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.025,
            f"{t['test_matches_training_satellite']}/{t['test_count']}",ha='center',fontsize=8)
    ax.set(xticks=np.arange(3),xticklabels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s'],
        ylim=(0,1.15),ylabel='Fraction of all held trajectory points',title='Forward fold' if fold==folds[0] else 'Reverse fold')
    ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
fig.suptitle('Refitting the existing receiver-band contrast barely changes held recovery\n'
             'Fitted c; actual frozen classifier; missing groups stay in the denominator')
fig.savefig(HERE/'01_held_coherence.png',dpi=180)
fig=Figure(figsize=(11,4.2),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for ax,fold in zip(axes,folds):
    gains=[];accepted=[]
    for arm in ['fitted-c','zero-c']:
        result=rows[(fold,arm)];old=next(r for r in result['variants'] if r['variant']=='frozen');new=next(r for r in result['variants'] if r['variant']=='joint')
        gains.append(old['audit']['objective']-new['audit']['objective']);accepted.append(new['audit']['accepted'])
    bars=ax.bar(np.arange(2),gains,color=['#167f9b','#dc7824'])
    for bar,value,ok in zip(bars,gains,accepted):
        if not ok:bar.set_hatch('//');bar.set_alpha(.5)
        ax.text(bar.get_x()+bar.get_width()/2,value+5,str(round(value))+('' if ok else ' · rejected'),ha='center',fontsize=8)
    ax.set(xticks=np.arange(2),xticklabels=['Fitted c','Refitted c = 0'],ylim=(0,520),ylabel='Training objective decrease',
        title='Forward fold' if fold==folds[0] else 'Reverse fold');ax.grid(axis='y',alpha=.2)
fig.suptitle('Lower training score does not establish better trajectory recovery\nHatching marks the original numerical gate failing; no position accuracy claim')
fig.savefig(HERE/'02_training_objective.png',dpi=180)
(HERE/'summary.json').write_text(json.dumps([dict(fold=fold,arm=arm,transport=d['transport'],variants=d['variants']) for (fold,arm),d in rows.items()],indent=2)+'\n')
files=[dict(path=str(p.relative_to(HERE)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts]
(HERE/'manifest.json').write_text(json.dumps(dict(scope='Matched research controls; no independently verified identity or position truth.',files=files),indent=2)+'\n')
print(json.dumps(dict(files=len(files),results=[dict(fold=fold,arm=arm,
    audits=[(r['variant'],r['audit']['accepted']) for r in d['variants']]) for (fold,arm),d in rows.items()])))
