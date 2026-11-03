"""Extend the historical A/B figure with separately labeled N01/N02 results."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

HERE = Path(__file__).resolve().parent
WORK = Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')
OLD = HERE.parent/'2026_10_04_ds13_association_review/subset-position-search/summary.csv'
NAMES = {'rms':'Lowest satellite RMS','support':'Most windows per satellite','glrt':'Highest window GLRT score'}
COLORS = {'fitted-c':'#0077ad','zero-c':'#df6900'}


def read_rows():
    rows = []
    for r in csv.DictReader(OLD.open()):
        rows.append(dict(scan=r['scan'],ranking=r['ranking'],fraction=float(r['fraction']),arm=r['arm'],
             distance_m=float(r['distance_m']),east_m=float(r['east_m']),north_m=float(r['north_m']),
             windows=int(r['windows']),candidates=int(r['candidates']),
             boundary=r['boundary_limited']=='True',converged=r['polish_unconverged']=='False',
             ambiguous=any(r[k]=='True' for k in ('ambiguity','lower_point_after_neighbors')),
             delta_score=float(r['delta_score']),source=str(OLD.parent/r['source']),provenance='Historical A/B'))
    for scan in ('N01','N02'):
        for ranking in NAMES:
            for fraction in (.25,.5,.75,1.):
                case = 'all-100' if fraction == 1 else f'{ranking}-{int(100*fraction)}'
                path = WORK/scan/f'{case}.json'
                result = json.loads(path.read_text())
                for arm,r in result['arms'].items():
                    rows.append(dict(scan=scan,ranking=ranking,fraction=fraction,arm=arm,
                         distance_m=r['distance_m'],east_m=1000*r['best']['point_km'][0],north_m=1000*r['best']['point_km'][1],
                         windows=result['windows'],candidates=result['candidates'],
                         boundary=r['boundary'],converged=r['converged'],ambiguous=r['ambiguous'],
                         delta_score=r['delta_score'],source=str(path),provenance='New bounded Fisher/SQP search'))
    return rows


def plot(rows, scans, filename):
    fig,axes = plt.subplots(len(scans),3,figsize=(16,4.5*len(scans)+1.8),sharex=True,sharey=True,squeeze=False)
    for i,scan in enumerate(scans):
        for j,(ranking,title) in enumerate(NAMES.items()):
            ax = axes[i,j]
            for arm,color in COLORS.items():
                entries = sorted([r for r in rows if r['scan']==scan and r['ranking']==ranking and r['arm']==arm],key=lambda r:r['fraction'])
                x = [100*r['fraction'] for r in entries]
                y = [r['distance_m'] for r in entries]
                ax.plot(x,y,'-',color=color,lw=1.7,alpha=.8)
                for r,xx,yy in zip(entries,x,y):
                    marker = 'X' if not r['converged'] else '^' if r['boundary'] else '*' if r['ambiguous'] else 'o'
                    ax.scatter([xx],[yy],marker=marker,s=110 if marker in ('X','*') else 60,
                               c=color,edgecolors='black' if marker!='o' else color,zorder=5)
                    peer = next(q for q in rows if q['scan']==scan and q['ranking']==ranking and q['fraction']==r['fraction'] and q['arm']!=arm)
                    above = yy >= peer['distance_m'] if yy != peer['distance_m'] else arm=='fitted-c'
                    ax.annotate(f'{yy:.0f}',(xx,yy),xytext=(0,10 if above else -17),textcoords='offset points',
                                ha='center',fontsize=8,color=color)
            label = 'historical reference' if scan in ('A','B') else 'new T1-AT associations'
            ax.set_title(f'{scan} · {label}\n{title}',fontsize=11)
            ax.axhline(2000,color='.5',ls=':',lw=1)
            ax.set_ylim(-100,2210);ax.set_xlim(20,105);ax.set_xticks([25,50,75,100]);ax.tick_params(labelbottom=True)
            ax.set_xlabel('Top fraction retained (%)');ax.grid(alpha=.2)
            if j==0:ax.set_ylabel('Best-found distance from roof (m)')
    fig.suptitle('T1-AT · association subsets: independent 2 km position searches',fontsize=18,y=.985)
    handles=[Line2D([],[],color=c,marker='o',label='Fitted c' if a=='fitted-c' else 'c = 0') for a,c in COLORS.items()]
    handles += [Line2D([],[],color='black',ls='',marker=m,label=l) for m,l in [('^','Boundary'),('*','Search ambiguity'),('X','Not converged / not a minimum')]]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.966),ncol=5,frameon=False)
    fig.text(.5,.025,'Each scan independent. Fitted-c memberships/rankings fixed at roof; identical subsets and budgets in both RF arms.\n'
             '100% means assigned windows only. Satellite rankings retain satellites; GLRT ranking retains windows. Best found, not global certification.\n'
             'A/B numerical results retained; status markers audited. N01/N02 use 3-start Fisher/SQP; budgets differ from historical A/B.\n'
             'Frozen fitted-c RX baseline shared in RF arms; extra RX lines, RF coefficient and absolute timing refitted with Gaussian timing priors.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.105 if len(scans)==2 else .075,1,.94))
    fig.savefig(HERE/filename,dpi=160);plt.close(fig)


def coverage_plot():
    rows = list(csv.DictReader((HERE/'summary.csv').open()))
    fig,axes = plt.subplots(1,2,figsize=(10,4.5),sharey=True)
    for ax,scan in zip(axes,('N01','N02')):
        selected=[next(r for r in rows if r['scan']==scan and r['arm']==a) for a in COLORS]
        for offset,key,label,color in [(-.18,'previous_top_coverage','Previous top-only','#9a9a9a'),(.18,'coverage','T1-AT v1','#0077ad')]:
            values=[100*float(r[key]) for r in selected]
            bars=ax.bar(np.arange(2)+offset,values,.36,color=color,label=label)
            ax.bar_label(bars,labels=[f'{v:.1f}%' for v in values],padding=4)
        ax.set_title(scan);ax.set_xticks([0,1],['Fitted c','c = 0']);ax.set_ylim(0,100)
        ax.set_ylabel('Passing windows associated (%)');ax.grid(axis='y',alpha=.2)
    axes[0].legend(loc='lower left');fig.suptitle('Window coverage · same denominator within each scan')
    fig.tight_layout();fig.savefig(HERE/'coverage-comparison.png',dpi=160);plt.close(fig)


if __name__ == '__main__':
    rows = read_rows()
    with (HERE/'subset-position-summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    plot(rows,('A','B','N01','N02'),'subset-position-AB-N01-N02.png')
    plot(rows,('N01','N02'),'subset-position-N01-N02.png')
    coverage_plot()
    print('Rendered',len(rows),'rows; unique new cases',len({r['source'] for r in rows if r['scan'].startswith('N')}))
