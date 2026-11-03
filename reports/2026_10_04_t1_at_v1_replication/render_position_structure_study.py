"""Publication layout from audited CSVs only; no fitting or metric changes."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent/'position-structure-study'/'polished'
LABELS={
 'C1':'Reference', 'A01':'Satellite-balanced', 'A02':'Satellite/RX-balanced',
 'A03':'5-second density balancing', 'A04':'GLRT-confidence weighting',
 'A05':'Student-t frequency errors', 'A06':'Narrow/broad Gaussian mixture',
 'A07':'Original owner or clutter', 'A08':'Independent RX drift priors',
 'A09':'Relative RX drift prior', 'A10':'Per-RX quadratic drift',
}


def render():
    with (ROOT/'per-scan.csv').open() as f: rows=list(csv.DictReader(f))
    with (ROOT/'summary.csv').open() as f: summaries=list(csv.DictReader(f))
    assert len(rows)==352
    lookup={(r['scan'],r['arm'],r['mode']):r for r in rows}
    scans=[f'N{i:02}' for i in range(1,17)]
    modes=['C1']+[r['mode'] for r in sorted(summaries,key=lambda r:float(r['median_error_m']))
                  if r['arm']=='fitted-c' and r['mode']!='C1']
    fig=plt.figure(figsize=(21,9))
    grid=fig.add_gridspec(1,3,width_ratios=[1,1,.025],left=.19,right=.96,bottom=.17,top=.87,wspace=.07)
    axes=[fig.add_subplot(grid[0,i]) for i in range(2)]
    for ax,arm in zip(axes,['fitted-c','zero-c']):
        values=np.array([[float(lookup[s,arm,m]['distance_m']) for s in scans] for m in modes])
        im=ax.imshow(values,vmin=0,vmax=4000,cmap='viridis_r',aspect='auto')
        for j,m in enumerate(modes):
            for i,s in enumerate(scans):
                r=lookup[s,arm,m];distance=float(r['distance_m'])
                label=f'{distance/1000:.2f}'+('△' if r['boundary']=='True' else '')+('×' if r['converged']!='True' else '')
                ax.text(i,j,label,ha='center',va='center',fontsize=7.3,color='white' if distance>2200 else 'black')
        ax.set_xticks(range(16),scans,rotation=60)
        ax.set_yticks(range(len(modes)))
        ax.set_yticklabels([m+' · '+LABELS[m] for m in modes] if arm=='fitted-c' else [])
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0',fontsize=14)
        ax.axhline(.5,color='white',lw=2)
    fig.colorbar(im,cax=fig.add_subplot(grid[0,2]),label='Position error (m)')
    fig.suptitle('Ten structural approaches · N01–N16 independent 4 km position searches',fontsize=19)
    fig.text(.57,.925,'Same full-data inputs and RF ablation · one fixed approach per row across all scans',ha='center',fontsize=12)
    fig.text(.5,.05,'Cell numbers = km. △ = 4 km boundary; × = unconverged. All cases retained.\n'
        'In-sample development with known-roof upstream calibration; best-found bounded solutions, not global certificates.',ha='center',fontsize=10)
    fig.savefig(ROOT/'position-errors.png',dpi=180)
    plt.close(fig)


if __name__=='__main__':render()
