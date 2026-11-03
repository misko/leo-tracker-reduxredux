"""Render completed pilot evidence without implying the campaign is complete."""
import argparse
import json
from pathlib import Path

import numpy as np

from cohort import digest
from refinement import circular


def validate_comparison(result, penalty=10.):
    if result['denominator']<=0 or result['assigned']+result['unassigned']!=result['denominator']:
        raise ValueError('invalid window accounting')
    if not np.isclose(result['coverage'],result['assigned']/result['denominator']):
        raise ValueError('coverage does not match counts')
    if not np.isclose(result['objective'],result['assigned']-penalty*result['satellites']):
        raise ValueError('penalized objective mismatch')


def render(directory, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    selection=directory/'selection-p10-g600-t1.json'
    refined=directory/'refinement/refined.json'
    observations=directory/'observations.json'
    saved=json.loads(selection.read_text())
    source=json.loads(observations.read_text())
    changed=json.loads(refined.read_text())
    if changed['summary']['signature']['observations_sha256']!=digest(observations.read_bytes()):
        raise ValueError('refinement provenance mismatch')
    output.mkdir(exist_ok=True,parents=True)
    methods=('greedy','replacement','alternatives')
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    x=np.arange(3)
    table=[]
    for offset,arm,color in ((-.18,'fitted-c','#0072b2'),(.18,'zero-c','#d55e00')):
        results=[saved['arms'][arm][method]['final'] for method in methods]
        for result in results:
            validate_comparison(result)
        for ax,key,title in zip(axes,('coverage','satellites','objective'),('Associated passing windows (%)','Selected satellites','Windows − 10 × satellites')):
            values=[r[key]*(100 if key=='coverage' else 1) for r in results]
            bars=ax.bar(x+offset,values,.34,label=arm,color=color)
            ax.bar_label(bars,labels=[f'{v:.1f}' if key=='coverage' else f'{v:g}' for v in values],padding=4,fontsize=10)
            ax.set_title(title)
            ax.set_xticks(x,('Greedy','+ replacement','+ alternatives'))
            ax.set_ylim(0,max(values+[1])*1.2 if key!='coverage' else 100)
            ax.grid(axis='y',alpha=.2)
            ax.set_axisbelow(True)
        for method,r in zip(methods,results):
            table.append(dict(arm=arm,method=method,**{k:r[k] for k in ('assigned','unassigned','denominator','coverage','satellites','objective')}))
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.885),ncol=2)
    for ax,key in zip(axes[1:],('satellites','objective')):
        ax.set_ylim(0,max(r[key] for r in table)*1.2)
    fig.suptitle(f'{directory.name} · pilot association comparison\nSame original passing windows; shared exhaustive satellite/timing pool',fontsize=15)
    fig.text(.5,.018,'Conditional known-roof, in-sample satellite selection. Higher coverage is not confirmed identity or better localization.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.06,1,.88))
    fig.savefig(output/'association-comparison.png',dpi=150)
    plt.close(fig)
    records=changed['records']
    before=np.array([r['original_margin'] for r in records])
    after=np.array([r['refinement'].get('margin',r['original_margin']) for r in records])
    delta=np.array([float(circular(r['output_hz']-r['original_hz'])) for r in records])
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    axes[0].hist(delta,bins=np.linspace(-1000,1000,81),color='#0072b2')
    axes[0].set(xlabel='Alias-aware frequency update (Hz)',ylabel='Candidate records',title='Orbit-blind frequency refinement')
    axes[1].hist(before,bins=np.linspace(0,1,51),histtype='step',label='Before',color='#d55e00',lw=1.6)
    axes[1].hist(after,bins=np.linspace(0,1,51),histtype='step',label='After',color='#0072b2',lw=1.6)
    axes[1].set(xlabel='GLRT margin',ylabel='Candidate records',title='Same saved passing candidates')
    axes[1].legend()
    values=[len(records),len(changed['top_rows'])]
    bars=axes[2].bar(['Saved candidates','Top candidate / window'],values,color=['#888888','#0072b2'])
    axes[2].bar_label(bars,padding=4)
    axes[2].set_ylim(0,max(values)*1.2)
    axes[2].set_title('Candidates are not windows')
    fig.suptitle(f'{directory.name} · refinement and accounting',fontsize=15)
    fig.text(.5,.01,'Alias copies remain in saved candidate counts. Failed refinement retains the original.\nFrequency-update panel displays ±1 kHz; score panel displays [0,1]. Not a rerun of originally rejected candidates.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.10,1,.9))
    fig.savefig(output/'refinement-comparison.png',dpi=150)
    plt.close(fig)
    metrics=dict(status='pilot_associations_only',scan=directory.name,session_id=source['summary']['session_id'],
                 variant=directory.name if directory.name.startswith('seed-timing-') else 'initial-bootstrap',
                 calibration_warnings=saved.get('calibration_warnings',[]),
                 comparisons=table,refinement=changed['summary'],
                 outside_frequency_panel=int(sum(abs(delta)>1000)),outside_margin_panel=int(sum((after<0)|(after>1))),
                 sources={str(p):digest(p.read_bytes()) for p in (selection,refined,observations,Path(__file__))})
    (output/'pilot-metrics.json').write_text(json.dumps(metrics,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    render(a.directory,a.output)
