"""Visualize a sealed local-curvature coverage diagnostic without tuning it."""
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
    result=json.loads(args.input.read_text());output=args.input.with_suffix('.png');assert not output.exists()
    fig,axes=plt.subplots(1,2,figsize=(11,4.8),constrained_layout=True)
    colors=['#3178a8','#df8535','#37936b'];labels=['Singles','Pairs','Quads']
    for index,size in enumerate([1,2,4]):
        summary=result['summary'][str(size)];n=summary['shape_available'];inside=summary['inside_nominal95']
        axes[0].bar(index,inside/n if n else 0,color=colors[index],width=.6)
        axes[0].text(index,(inside/n if n else 0)+.025,f'{inside}/{n}',ha='center')
        rows=[r for r in result['rows'] if r['size']==size and r['shape_available']]
        offsets=np.linspace(-.18,.18,len(rows)) if len(rows)>1 else np.zeros(len(rows))
        axes[1].scatter(index+offsets,[max(r['mahalanobis_squared'],1e-8) for r in rows],color=colors[index],s=30,alpha=.8)
    axes[0].axhline(.95,color='black',linestyle='--',label='Nominal 95%')
    axes[0].set_ylim(0,1.08);axes[0].set_ylabel('Fraction containing operator reference')
    axes[0].set_title('Coverage among available local ellipses');axes[0].legend()
    axes[1].axhline(5.991464547107979,color='black',linestyle='--',label='Nominal 95% ellipse threshold')
    axes[1].set_yscale('log');axes[1].set_ylabel('Squared normalized position error')
    axes[1].set_title('One point per accepted fit with available geometry');axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_xticks([0,1,2],labels);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Local IRLS curvature is an uncertainty diagnostic, not a calibrated guarantee\nCorrelated development windows; fixed fitted assignments and unsurveyed reference',fontsize=11)
    fig.savefig(output,dpi=160)


if __name__=='__main__':main()
