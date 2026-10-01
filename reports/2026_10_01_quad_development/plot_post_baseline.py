"""Display the separately evaluated recovery, initialization and numerical variants."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('input',type=Path);args=parser.parse_args()
    assert digest(args.input)==args.input.with_suffix('.sha256').read_text().strip()
    data=json.loads(args.input.read_text());output=args.input.with_suffix('.png');assert not output.exists()
    fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
    for offset,arm,color,label in [(-.18,'baseline','#8c969f','Baseline'),(.18,'baseline_plus_continuation','#3178a8','With continuation')]:
        stats=[data['summary'][arm][str(size)] for size in [1,2,4]]
        values=[s['accepted']/s['planned'] for s in stats]
        axes[0].bar(np.arange(3)+offset,values,width=.34,color=color,label=label)
        for index,(value,s) in enumerate(zip(values,stats)):
            axes[0].text(index+offset,value+.025,f"{s['accepted']}/{s['planned']}",ha='center',fontsize=8)
    axes[0].set_xticks([0,1,2],['Singles','Pairs','Quads']);axes[0].set_ylim(0,1.15)
    axes[0].set_ylabel('Fraction numerically accepted');axes[0].set_title('Recovery; all planned windows');axes[0].legend(loc='lower left')
    for index,entry in enumerate(data['pair_comparisons']):
        original,variant=entry['baseline'],entry['variant']
        values=[r['error_m'] if r['accepted'] else np.nan for r in [original,variant]]
        color='#df8535' if entry['selection']=='failure_selected' else '#3178a8'
        axes[1].plot([index-.12,index+.12],values,'-',color=color,alpha=.6)
        if original['accepted']:axes[1].scatter(index-.12,values[0],marker='x',color='black',s=60)
        if variant['accepted']:axes[1].scatter(index+.12,values[1],marker='o',color=color,s=45)
        else:axes[1].text(index,.04,'failed',transform=axes[1].get_xaxis_transform(),ha='center',fontsize=8)
    axes[1].set_xticks(range(len(data['pair_comparisons'])),[p['unit'] for p in data['pair_comparisons']],rotation=25,ha='right')
    axes[1].set_yscale('log');axes[1].set_ylabel('Horizontal error (m, log scale)')
    axes[1].set_title('Pair starts: × baseline, ● constituent\nOrange case was selected after failure',fontsize=10)
    gates=data['cold_blas_comparisons']
    for index,gate in enumerate(gates):
        ratio=gate['baseline_runtime_s']/gate['optimized_runtime_s']
        axes[2].bar(index,ratio,color='#37936b' if gate['equivalent'] else '#b94a48')
        axes[2].text(index,ratio+.025,'equivalent' if gate['equivalent'] else 'gate failed',ha='center',fontsize=8)
    axes[2].set_xticks(range(len(gates)),[g['unit'] for g in gates],rotation=25,ha='right')
    axes[2].axhline(1,color='black',linestyle='--');axes[2].set_ylabel('Historical baseline / new wall time')
    axes[2].set_title('Cold acquisition gate\nTiming is not a randomized comparison',fontsize=10)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle('Separate development experiments; these changes are not a combined validated estimator',fontsize=12)
    fig.savefig(output,dpi=160)


if __name__=='__main__':main()
