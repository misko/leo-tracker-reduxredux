"""Paired audited clock ablation for one complete pilot block."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('block');args=parser.parse_args()
    sources={};arms={}
    for arm,folder in [('independent','independent-v2'),('common','common-clock-v1')]:
        path=HERE/folder/args.block/'evaluation.json'
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        sources[str(path)]=digest(path)
        arms[arm]={r['unit']:r for r in json.loads(path.read_text())['rows']}
    comparisons=[]
    for suffix in ['-D1','-D2','-Q']:
        unit=args.block+suffix;left=arms['independent'][unit];right=arms['common'][unit]
        comparisons.append(dict(unit=unit,independent=left,common=right,
            error_change_m=right['error_m']-left['error_m'] if left['accepted'] and right['accepted'] else None))
    clock_values={}
    for arm,folder in [('independent','independent-v2'),('common','common-clock-v1')]:
        row=arms[arm][args.block+'-Q']
        if not row['accepted']:continue
        path=HERE/folder/args.block/(args.block+'-Q.json');assert digest(path)==row['receipt_sha256']
        data=json.loads(path.read_text());state=data['best']['mean']
        clock_values[arm]=[state[c[2]] for c in data['columns']]
    result=dict(block=args.block,comparisons=comparisons,quad_clock_values_s=clock_values,
        source_sha256=sources,comparator_sha256=digest(__file__),
        qualification='Paired cold development ablation on one block. Same marginal1s clock prior; cross-scan dependence changes. Singles are mathematically identical and reused. Failures retained; no model promotion from one block.')
    output=HERE/('clock-comparison-'+args.block+'-v1.json')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    x=np.arange(3)
    for arm,offset,color in [('independent',-.18,'#3178a8'),('common',.18,'#df8535')]:
        for i,c in enumerate(comparisons):
            row=c[arm]
            if row['accepted']:
                axes[0].bar(i+offset,row['error_m'],.35,color=color,label=arm if i==0 else None)
                axes[0].text(i+offset,row['error_m'],f"{row['error_m']:.0f}",ha='center',va='bottom',fontsize=8)
            else:axes[0].text(i+offset,0,'FAILED',rotation=90,ha='center')
        if arm in clock_values:axes[1].plot(range(4),clock_values[arm],'-o',label=arm,color=color)
    axes[0].set_xticks(x,['AB','CD','ABCD']);axes[0].set_ylabel('Horizontal error (m)');axes[0].margins(y=.2)
    axes[1].set_xticks(range(4),['A','B','C','D']);axes[1].set_ylabel('Fitted clock shift in quad (s)')
    for ax in axes:ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle(args.block+' clock ablation: fresh acquisition and joint fits')
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps([dict(unit=c['unit'],change_m=c['error_change_m'],common_error_m=c['common']['error_m'],accepted=c['common']['accepted']) for c in comparisons],indent=2))


if __name__=='__main__':main()
