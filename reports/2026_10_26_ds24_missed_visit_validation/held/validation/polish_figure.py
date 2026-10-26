"""Reporting-only readback and unobscured legend placement; no scientific edits."""
from collections import Counter
import json
from pathlib import Path
import audit


def main():
    audit.bound();p=audit.HERE;s=audit.read(p/'summary.json')
    rows=[r for f in sorted((p/'case_audits').glob('*.json'))for r in audit.read(f)['cells']]
    earlier={r['header']['prediction_id']:r for r in audit.read(audit.PRED/'r01_prediction_packets.json')['rows']}
    two={r['prediction_id']:r for r in audit.read(audit.PRED/'r02_predictions.json')['rows']}
    data=dict(reporting_only=True,source_summary_sha256=audit.sha(p/'summary.json'),paired={},new_frequency={},new_donors={})
    for label,cohort in [('all',rows),('CH58',[r for r in rows if r['channel']>=5])]:
        data['paired'][label]=dict(quadratic_gain=sum(r['methods']['R02_quadratic_or_fallback']['admitted']and not r['methods']['R02_linear']['admitted']for r in cohort),
            quadratic_loss=sum(not r['methods']['R02_quadratic_or_fallback']['admitted']and r['methods']['R02_linear']['admitted']for r in cohort))
        for method in ['R01_search','R02_quadratic_or_fallback']:
            new=[r for r in cohort if not r['original']and r['methods'][method]['admitted']]
            values=[r['methods'][method]['innovation_hz']for r in new]
            data['new_frequency'][label+'/'+method]=dict(count=len(values),zero=sum(abs(v)<1e-8 for v in values),
                nonzero=sum(abs(v)>=1e-8 for v in values),max_absolute_hz=max(map(abs,values),default=None))
            counts=[len(earlier[r['prediction_id']]['forecast']['modes'][r['methods'][method]['selected_mode']]['donors'])if method=='R01_search'else len(two[r['prediction_id']]['donors'])for r in new]
            data['new_donors'][label+'/'+method]=dict(Counter(counts))
    audit.write(p/'comparison_readback.json',data)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    ch=[1,4,5,6,7,8];x=np.arange(6);fig,axes=plt.subplots(1,2,figsize=(12.4,4.9))
    base=[s['by_channel'][str(c)]['R01_search']['original']for c in ch]
    for j,(method,label,color)in enumerate([('original','Original','#6b7280'),('R01_search','Original + R01 search','#1d4ed8'),('R02_quadratic_or_fallback','Original + R02 point','#059669')]):
        v=base if method=='original'else[b+s['by_channel'][str(c)][method]['new']for b,c in zip(base,ch)]
        axes[0].bar(x+(j-1)*.25,v,.24,label=label,color=color)
    axes[0].set_ylabel('Detected owners / 96 held cells per channel');axes[0].set_title('Additions preserve every original detection')
    for j,(method,label,color)in enumerate([('R01_search','R01 search','#1d4ed8'),('R02_quadratic_or_fallback','R02 point','#059669')]):
        zero=[s['by_channel'][str(c)][method]['new_zero_bin']for c in ch]
        other=[s['by_channel'][str(c)][method]['new']-z for c,z in zip(ch,zero)]
        axes[1].bar(x+(j-.5)*.34,zero,.32,label=label+' zero bin',color=color,alpha=.42)
        axes[1].bar(x+(j-.5)*.34,other,.32,bottom=zero,label=label+' nonzero bin',color=color)
    axes[1].set_ylabel('New original-negative admissions');axes[1].set_title('Frequency innovations remain donor-centered')
    for ax in axes:
        ax.set_xticks(x,[f'CH{c}'for c in ch]);ax.spines[['right','top']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.13),ncol=2,fontsize=8,frameon=False)
    fig.suptitle('Frozen held application: R01 split confirmation vs R02 full-window primary point',fontsize=12)
    fig.subplots_adjust(bottom=.25,top=.83,wspace=.25,left=.065,right=.99)
    fig.savefig(p/'held_comparison_v2.png',dpi=170);fig.savefig(p/'held_comparison_v2.pdf');plt.close(fig)
    print(json.dumps(data),flush=True)


if __name__=='__main__':main()
