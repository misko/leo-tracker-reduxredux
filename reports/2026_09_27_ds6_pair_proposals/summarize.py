"""Illustrate candidate coverage and offset-model sensitivity."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def main():
    proposal=json.loads((HERE/'results.json').read_text());full=json.loads((HERE/'full-results.json').read_text());zero=json.loads((HERE/'zero-offset-results.json').read_text())
    assert full['complete'] and zero['complete']
    rows=[];fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    names=['restricted','256','512','1024','full','zero offset'];times=np.arange(-5.,6.)
    for i,(p,f,z) in enumerate(zip(proposal['scans'],full['scans'],zero['scans'])):
        assert p['session_id']==f['session_id']==z['session_id']
        arms={name:p['arms'][name] for name in names[:4]};arms.update(full=f,**{'zero offset':z})
        scores={name:dict(held_phase=a['geometry']['held_phase_log_predictive'],
            geometry_minus_constant=a['geometry']['held_phase_log_predictive']-a['response_only']['held_phase_log_predictive'],
            cfo_only_held=a['geometry']['cfo_only_held_log_predictive'],phase_gain_in_held_cfo=a['geometry']['held_cfo_log_predictive']-a['geometry']['cfo_only_held_log_predictive']) for name,a in arms.items()}
        rows.append(dict(session_id=p['session_id'],scores=scores,full_pair_time_evaluations=sum(sum(g['pair_counts']) for g in f['groups']),
                         retention=f['retention'],zero_offset_held_cfo_change=scores['zero offset']['cfo_only_held']-scores['full']['cfo_only_held']))
        x=np.arange(len(names));labels=['Old\nunion','256','512','1024','All\npairs','Zero\noffset']
        axes[i,0].bar(x,[scores[n]['cfo_only_held']-scores['restricted']['cfo_only_held'] for n in names],color=['0.6']+['tab:blue']*4+['tab:orange'])
        axes[i,0].set(xticks=x,xticklabels=labels,ylabel='Held differential-CFO score gain',title=p['session_id'][-8:]+' — same held CFO target')
        axes[i,1].bar(x,[scores[n]['geometry_minus_constant'] for n in names],color=['0.6']+['tab:blue']*4+['tab:orange']);axes[i,1].axhline(0,color='black',lw=.7)
        axes[i,1].set(xticks=x,xticklabels=labels,ylabel='Held phase: geometry minus constant',title='Positive favors orbital geometry')
        axes[i,2].plot(times,p['arms']['restricted']['geometry']['cfo_only_time_posterior'],label='Old union')
        axes[i,2].plot(times,f['geometry']['cfo_time_posterior'],label='All pairs, free offset')
        axes[i,2].plot(times,z['geometry']['cfo_time_posterior'],label='All pairs, zero offset')
        axes[i,2].set(xlabel='Scan timing offset (s)',ylabel='Conditional timing probability',title='Concentration depends strongly on model')
        axes[i,2].legend(fontsize=8)
    fig.suptitle('DS6: exhaustive visible-pair audit changes the apparent evidence for orbital phase')
    fig.savefig(HERE/'pair-coverage-and-prediction.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained');ret=[r for scan in full['scans'] for r in scan['retention']];x=np.arange(len(ret))
    for offset,k in [(-.25,'256'),(0,'512'),(.25,'1024')]:ax.bar(x+offset,[r['mass'][k] for r in ret],width=.25,label=k+' SSE proposals')
    ax.set(xticks=x,xticklabels=['a2465361\nCH3','a2465361\nCH2','ae9e08b0\nCH3','ae9e08b0\nCH2'],ylim=(0,1.1),ylabel='Fraction of full CFO probability mass retained',title='The weakest pair loses 79% of its mass even with 1,024 proposals')
    ax.legend(fontsize=8)
    fig.savefig(HERE/'retained-mass.png',dpi=160);plt.close(fig)
    out=dict(scans=rows,full_elapsed_s=full['elapsed_s'],zero_elapsed_s=zero['elapsed_s'],scope='Fixed-observer predictive audit only; no new position estimate')
    (HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
