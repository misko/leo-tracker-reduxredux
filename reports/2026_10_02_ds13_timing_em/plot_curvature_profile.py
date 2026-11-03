"""Render saved score probes with a common color scale and separated labels."""
import json
import numpy as np
from curvature_position_profile import ROOT


def run():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory=ROOT/'curvature-filter-roof-profile'
    receipt=json.loads((directory/'receipt.json').read_text())
    fig,axes=plt.subplots(2,3,figsize=(15,11),sharex=True,sharey=True)
    limit=max(abs(c['delta_score']) for item in receipt['combined'].values() for c in item['cells'])
    for row,variant in enumerate(('unfiltered','filtered')):
        for col,label in enumerate(('A','B','combined')):
            item=receipt['combined'][variant] if label=='combined' else next(r for r in receipt['results'] if r['scan']==label)['variants'][variant]
            cells=item['cells'];ax=axes[row,col]
            im=ax.scatter([c['east_m'] for c in cells],[c['north_m'] for c in cells],
                c=[c['delta_score'] for c in cells],cmap='RdBu_r',vmin=-limit,vmax=limit,s=85,edgecolors='.4')
            for c in cells:
                if c['label'].startswith('random'):
                    ax.annotate(f"{c['delta_score']:+.2f}",(c['east_m'],c['north_m']),
                                xytext=(5,5),textcoords='offset points',fontsize=9)
            g=np.asarray(item['derivatives'][0]['gradient_score_per_m'])
            ax.plot(0,0,'k+',ms=16,mew=2)
            if np.linalg.norm(g):
                ax.arrow(0,0,*(-g/np.linalg.norm(g)*180),width=3,head_width=22,color='black',length_includes_head=True)
            ax.set_title(f"{'Combined' if label=='combined' else 'Scan '+label} · {variant}\n"
                f"Gradient per 100 m: E {100*g[0]:+.2f}, N {100*g[1]:+.2f}",fontsize=11,pad=12)
            ax.set_aspect('equal');ax.set_xlim(-550,550);ax.set_ylim(-550,550);ax.grid(alpha=.18)
            ax.set_xlabel('East of roof (m)');
            if col==0:ax.set_ylabel('North of roof (m)')
    fig.subplots_adjust(left=.07,right=.90,bottom=.13,top=.86,hspace=.36,wspace=.22)
    cax=fig.add_axes([.925,.20,.016,.59]);fig.colorbar(im,cax=cax,label='Score − roof score (lower is better)')
    fig.suptitle('DS13 · curvature filter does not remove the local position bias',fontsize=17,y=.965)
    fig.text(.5,.917,'RX offsets/drifts, RF correction and satellite timing refitted at every point',ha='center',fontsize=12)
    fig.text(.5,.045,'+ = correct roof location. Arrow = local downhill direction; fixed display length. Shared color scale.\n'
        'Six reproducible random points within 500 m + cardinal probes at ±50 m and ±100 m.\n'
        'Filter: exclude a satellite if any receiver track has linear-RMS / quadratic-RMS > 1.1 at the roof; freeze exclusions across sites.',
        ha='center',fontsize=10)
    fig.savefig(directory/'score-gradient-readable.png',dpi=170)
    plt.close(fig)


if __name__=='__main__':run()
