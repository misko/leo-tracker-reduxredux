"""Visualize optimizer changes without replacing frozen baseline results."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from continue_fits import OUT, REPORT
import factorial as study


def records(rows):
    keys=set(); output=[]
    for r in rows:
        key=tuple(r[k] for k in ('scan','refinement','model','cone','arm'))
        if key in keys: raise ValueError('Duplicate scientific case')
        keys.add(key)
        if r['original']['converged']: continue
        delta=r['objective']-r['original']['objective']
        if delta>1e-7: raise ValueError('Continuation increased objective')
        output.append(dict(label=' / '.join(key),
            before=r['original']['distance_m'], after=r['distance_m'],
            gain=-delta, converged=r['converged']))
    return output


def main():
    sources=sorted(OUT.glob('*/*/*/*/*.json'))
    rows=[]
    for p in sources:
        r=json.loads(p.read_text())
        assert study.stage.sha(r['source'])==r['continuation']['source_sha256']
        rows.append(r)
    data=records(rows)
    if not data: raise ValueError('No initially unconverged cases')
    fig,(ax,bx)=plt.subplots(1,2,figsize=(16,max(7,len(data)*.34)),
        gridspec_kw={'width_ratios':[1.3,1]})
    for i,r in enumerate(data):
        color='#0072B2' if r['converged'] else '#D55E00'
        ax.plot([r['before'],r['after']],[i,i],color=color,lw=2)
        ax.scatter(r['before'],i,marker='o',facecolors='white',edgecolors=color,s=36,zorder=3)
        ax.scatter(r['after'],i,marker='o' if r['converged'] else 'x',color=color,s=24,zorder=4)
        bx.barh(i,r['gain'],color=color,height=.6)
    ax.set_yticks(np.arange(len(data)),[r['label'] for r in data],fontsize=8)
    bx.set_yticks(np.arange(len(data)),[])
    for a in (ax,bx):
        a.set_ylim(len(data)-.5,-.5);a.grid(axis='x',alpha=.2);a.set_axisbelow(True)
    ax.set_xlim(0,4150);ax.axvline(4000,color='gray',ls=':',lw=1)
    ax.set_xlabel('Position error from roof (m)');ax.set_title('Open circle: before; filled circle or cross: after')
    bx.set_xscale('symlog',linthresh=.01)
    bx.set_xlabel('Reduction in the same objective (symlog scale)')
    bx.set_title('Blue: converged; orange: still provisional')
    fig.suptitle('Optimizer continuation · initially unconverged fits only')
    fig.text(.5,.015,'Identical observations, model and priors per before/after pair. '
        'Raw loss reductions across different models are not directly comparable.\n'
        'Lower loss does not necessarily reduce position error. The 4 km constraint is unchanged.',
        ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.065,1,.96))
    target=REPORT/'continuation-effects.png';fig.savefig(target,dpi=160);plt.close(fig)
    print(target)


if __name__=='__main__': main()
