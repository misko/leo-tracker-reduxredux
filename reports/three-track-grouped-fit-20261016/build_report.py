"""Build static figures and copy the executed research evidence into this report."""
import hashlib,json,shutil
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import ListedColormap

HERE=Path(__file__).resolve().parent
CAPSULE=HERE.parent/'three-track-recovery-replay-20261016'
RESULTS=HERE/'results';RESULTS.mkdir(exist_ok=True)
for folder in Path('/tmp/three-track-investigation').glob('cold-fold-*-v1'):
    for path in folder.glob('grouped_fit_*.json'):
        shutil.copy2(path,RESULTS/(folder.name+'_'+path.name))
for path in Path('/tmp/three-track-grouped-portable').glob('*.json'):
    shutil.copy2(path,RESULTS/path.name)

numbers=[69433,69333,69522];folds=['early_to_late','late_to_early'];audit=[]
for fold in folds:
    folder=CAPSULE/'checkpoints'/fold
    terminal=json.loads((folder/'terminal.json').read_text())
    points=[(p,json.loads(p.read_text())) for p in (folder/'stages').glob('discovery-point:*.json')]
    initial=sorted({n for _,row in points for n in row['catalogue_numbers']})
    final=terminal['candidate_numbers']
    audit.append(dict(fold=fold,discovery_candidates=initial,final_candidates=final,
        terminal_sha256=hashlib.sha256((folder/'terminal.json').read_bytes()).hexdigest(),
        hypotheses=[dict(satellite=n,discovery_point_count=sum(n in r['catalogue_numbers'] for _,r in points),
                         proposed=n in initial,retained=n in final) for n in numbers]))
(HERE/'candidate_retention_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
fig=Figure(figsize=(10,3.7),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for ax,key,title in zip(axes,['proposed','retained'],['Cold discovery-point union','Final candidate bank']):
    values=np.array([[h[key] for h in row['hypotheses']] for row in audit],int)
    ax.imshow(values,cmap=ListedColormap(['#e3a29b','#90c7ab']),vmin=0,vmax=1,aspect='auto')
    for y in range(2):
        for x in range(3):ax.text(x,y,'Present' if values[y,x] else 'Absent',ha='center',va='center')
    ax.set(xticks=np.arange(3),xticklabels=['Early CH2\n69433','CH4\n69333','Late CH2\n69522'],
           yticks=np.arange(2),yticklabels=['Forward fold\n103 → 54 candidates','Reverse fold\n105 → 60 candidates'],title=title)
fig.suptitle('A plausible candidate can disappear after cold discovery\nIDs are forward-consistent hypotheses, not independently verified identity labels')
fig.savefig(HERE/'01_candidate_retention.png',dpi=180)

fig=Figure(figsize=(12,4.6),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
labels=['CH2 · 50–75 s','CH4 · 40–100 s','CH2 · 170–190 s'];x=np.arange(3);summaries=[]
for j,fold in enumerate(folds):
    for offset,variant,color in [(-.18,'coherent','#167f9b'),(.18,'independent','#dc7824')]:
        suffix='closure_polished' if fold=='early_to_late' else 'closure_pass2'
        path=RESULTS/f'{fold}_{variant}_fitted-c_{suffix}.json';d=json.loads(path.read_text());summaries.append(dict(file=str(path.relative_to(HERE)),fold=fold,variant=variant,audit=d['audit'],tracks=d['tracks']))
        bars=axes[j].bar(x+offset,[t['test_rms_hz'] for t in d['tracks']],.36,color=color,
                        alpha=1 if d['audit']['accepted'] else .55,hatch=None if d['audit']['accepted'] else '//',
                        label=variant+(' · accepted' if d['audit']['accepted'] else ' · rejected'))
        for bar,track in zip(bars,d['tracks']):axes[j].text(bar.get_x()+bar.get_width()/2,bar.get_height()*1.06,str(round(track['test_rms_hz'])),ha='center',fontsize=8)
    axes[j].axhline(375,color='gray',lw=.8,ls=':');axes[j].set(xticks=x,xticklabels=labels,yscale='log',ylim=(70,4000),ylabel='Withheld carrier RMS (Hz)',title='Forward fold' if j==0 else 'Reverse fold');axes[j].legend(fontsize=8);axes[j].grid(axis='y',alpha=.2)
fig.suptitle('Grouped identity and training timing proposals do not yet solve both folds\nFitted c; hatching means the original numerical acceptance gate failed')
fig.savefig(HERE/'02_grouped_temporal_rms.png',dpi=180)
(HERE/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
priority=Path('/tmp/three-track-priority-low-reverse-20261016-v2')
for name in ['preparation-receipt.json','derivation.json','cold_candidate_temporal_transfer.json','cold_context_transport.json']:
    if (priority/name).exists():shutil.copy2(priority/name,HERE/('priority_low_'+name))
if (priority/'output/terminal.json').exists():shutil.copy2(priority/'output/terminal.json',HERE/'priority_low_terminal.json')
files=[dict(path=str(p.relative_to(HERE)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json']
(HERE/'manifest.json').write_text(json.dumps(dict(scope='Research grouped-track model, numerical qualifications and negative cold controls. No independent position or identity truth.',files=files),indent=2)+'\n')
print(json.dumps(dict(artifacts=len(files),results=len(list(RESULTS.glob('*.json'))))))
