"""Render deletion and regional-start diagnostics; reference is report-only."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from run_algo01_ds23_sample import ROOT, read, write
from report_algo02_ds23 import position_error, REFERENCE
from prototype_dsx01_continuous_position import CENTER

OUT = ROOT/'reports/2026_10_20_ds23_0041_influence'
ARMS = ('c0','fitted_c')


def main():
    protocol = read(OUT/'protocol.json')
    baseline = read(OUT/'baseline.json')
    rows = []
    for request in protocol['jobs']:
        document = read(OUT/(request['label']+'.json'))
        for arm in ARMS:
            r = document['arms'][arm]
            rows.append(dict(label=request['label'], arm=arm, error_km=position_error(r['endpoint_latlon']),
                paired_valid=document['paired_valid'], removed_curved_points=document['removed_curved_points'],
                removed_predictive_points=document['removed_predictive_points']))
    write(OUT/'evaluation.json',dict(rows=rows, GPS_used_only_for_reporting=True,
        deletion_not_a_validated_rejection_rule=True, no_scores_ranked_across_masks=True))
    labels = [r['label'] for r in protocol['jobs'] if r['label']!='baseline']
    fig,axes = plt.subplots(1,2,figsize=(12,10),sharey=True)
    for ax,arm in zip(axes,ARMS,strict=True):
        selected = [next(r for r in rows if r['arm']==arm and r['label']==label) for label in labels]
        bars = ax.barh(np.arange(len(labels)),[r['error_km'] for r in selected],color='#287b91')
        for bar,row in zip(bars,selected,strict=True):
            if not row['paired_valid']:
                bar.set_hatch('///');bar.set_alpha(.35)
        ax.axvline(position_error(baseline['arms'][arm]['endpoint_latlon']),color='black',ls='--',lw=1,label='Complete model')
        ax.set(xlabel='Position error after deletion (km)',title=arm)
        ax.grid(axis='x',alpha=.15);ax.legend(fontsize=9)
    axes[0].set_yticks(np.arange(len(labels)),[s.replace('drop_family_','Family ').replace('drop_','') for s in labels])
    axes[0].invert_yaxis()
    fig.suptitle('DS23-0041 · full-design causal influence diagnostics\nHatched fits fail paired gates; no single-family deletion fixes localization',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.93));fig.savefig(OUT/'family_receiver_ablation.png',dpi=180,bbox_inches='tight');plt.close(fig)
    reference = np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(REFERENCE[0]-CENTER[0])*111.])
    fig,axes = plt.subplots(2,2,figsize=(12,11),sharex=True,sharey=True)
    for column,mode in enumerate(('original','fine_reentry')):
        records = [read(OUT/f'multistart_{mode}_{i:02d}.json') for i in range(9)]
        for row,arm in enumerate(ARMS):
            ax = axes[row,column]
            for i,record in enumerate(records):
                r = record['arms'][arm]
                path = np.array([step['parameters'][:2] for epoch in r['history'] for step in epoch['fit']['history']])
                ax.plot(path[:,0],path[:,1],color='#765a8c',alpha=.5,lw=.9)
                start = record['request']['start']
                ax.scatter(*start,s=45,color='#b43d39',edgecolors='black',zorder=4,label='Independent start' if i==0 else None)
                ax.annotate(str(i),start,xytext=(4,4),textcoords='offset points',fontsize=8)
                ax.scatter(*r['endpoint_east_north_km'],marker='X',color='black',s=65,zorder=5,label='RF endpoint' if i==0 else None)
            ax.scatter(*reference,marker='*',color='#2a954c',s=160,zorder=6,label='Reference (report only)')
            error = position_error(records[0]['arms'][arm]['endpoint_latlon'])
            ax.set(xlim=(-12.5,12.5),ylim=(-12.5,12.5),aspect='equal',
                title=f'{mode} · {arm} · error {error:.2f} km',xlabel='East of regional center (km)',ylabel='North of regional center (km)')
            ax.grid(alpha=.2)
            if row==0 and column==0:ax.legend(fontsize=8,loc='upper left')
    fig.suptitle('DS23-0041 · nine independent starts per model and c arm\n'
                 'Fixed satellite identities during descent; every start finds the same incorrect minimum',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.93));fig.savefig(OUT/'regional_multistart.png',dpi=180,bbox_inches='tight');plt.close(fig)


if __name__=='__main__':
    main()
