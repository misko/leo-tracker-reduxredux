"""Static post-seal regional effect figure and compact final sensitivity receipt."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def main():
    evaluation=json.loads((HERE/'position_evaluation.json').read_text())
    cases=('DS24-0011','DS24-0097');fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    colors={'additions_proxy':'#4c78a8','additions_bin_floor':'#f58518'}
    x=np.arange(2);series=[]
    for k,(variant,arm,label) in enumerate([
        ('additions_proxy','c0','Proxy c=0'),('additions_proxy','fitted_c','Proxy fitted c'),
        ('additions_bin_floor','c0','Full-bin floor c=0'),('additions_bin_floor','fitted_c','Full-bin floor fitted c')]):
        values=[next(e for e in evaluation['effects'] if e['case']==case and e['variant']==variant)['arms'][arm]['position_error_change_km']*1000 for case in cases]
        axes[0].bar(x+(k-1.5)*.19,values,width=.18,label=label,color=colors[variant],alpha=1. if arm=='c0' else .55)
        series.append(dict(variant=variant,arm=arm,error_change_m=values))
    axes[0].axhline(0,color='.4',lw=1);axes[0].set_xticks(x,['DS24-0011','DS24-0097'])
    axes[0].set_ylabel('Position error change from fresh baseline (m)')
    axes[0].set_title('Small gains shrink with conservative new-point scales')
    axes[0].legend(frameon=False,fontsize=8)
    axes[1].bar(['New native\nowners','Curved graph\nowners','Causal curved\nlikelihood owners'],[15,8,5],color=['#f58518','#4c78a8','#e45756'])
    axes[1].set_ylabel('Distinct added owners, two selected cases')
    axes[1].set_title('Only a few recovered points enter position likelihood')
    for i,v in enumerate([15,8,5]):axes[1].text(i,v+.4,str(v),ha='center')
    axes[1].set_ylim(0,17)
    fig.suptitle('Fresh matched c-arm regional sensitivity: two RF-selected development cases')
    fig.text(.5,-.065,'All six jobs completed; GPS used only after terminal/input/read audit seals.\n'
        'Full-bin floor is an engineering sensitivity, not calibrated independent frequency uncertainty or promotion.',ha='center',fontsize=9)
    for ext in ('png','pdf'):fig.savefig(HERE/f'position_summary.{ext}',dpi=180,bbox_inches='tight')
    plt.close(fig)
    with (HERE/'position_summary.json').open('x') as stream:
        json.dump(dict(all_jobs_complete=True,cases=list(cases),matched_c_arms=True,effect_series=series,
            new_native=15,new_graph_curved=8,new_causal_curved=5,
            geographic_evaluation_after_seals=True,held_validation_claim=False,promotion=False),stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
