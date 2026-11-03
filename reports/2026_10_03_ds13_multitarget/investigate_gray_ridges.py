"""Trace the early scan-B RX1 gray ridges; diagnostic, not new assignments."""
import csv
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from exhaustive_subset import Case, HERE, circular_residual
from plot_tle_doppler_overlay import calibrated_points, orbital_curve
from plot_subset_orbits import alias_background
from prediction_jacobian import paired_prediction_jacobian


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ridge',choices=['main','lower','early','remaining_early','remaining_late'],default='main')
    ridge=parser.parse_args().ridge
    c=Case('B'); d=c.data
    out=HERE/'gray-ridge-audit'; out.mkdir(exist_ok=True)
    saved=json.loads((HERE/'exhaustive-subset/B-receipt.json').read_text())
    fit=saved['arms']['fitted-c']['fit']
    c.params=np.array(fit['parameters']);c.coeff=np.array(fit['rf_coefficient_hz_per_ghz'])
    c.selected=[int(np.flatnonzero(d.numbers==n)[0]) for n in saved['catalog_numbers']]
    records=list(csv.DictReader((HERE/'exhaustive-subset/B-fitted-c-assignments.csv').open()))
    assigned=np.array([int(r['row_index']) for r in records])
    pred,vis=c.predict(c.selected)
    rx=np.array(d.receiver,int)
    nuisance=c.params[2+2*rx]+c.params[3+2*rx]*(d.times-d.reference_time_s)+c.features@c.coeff
    points=calibrated_points(d.measured,pred,d.rf,nuisance,c.prepared.alias_hz)
    rr,cc=alias_background(points['alias_integer'],assigned)
    mask=(rx[rr]==1)&(d.times[rr]<=75)
    rr,cc=rr[mask],cc[mask]
    y=points['doppler_hz'][rr,cc]/1000
    # A deliberately broad visual extraction around the upper gray ridge.
    target=np.abs(y-(85-2.65*d.times[rr]))<10
    if ridge=='lower':
        target=(d.channel[rr]==4)&(d.times[rr]>30)&(d.times[rr]<60)&(y<5)&(y>-100)
    if ridge=='early':
        target=(d.channel[rr]==3)&(d.times[rr]<16)&(y>45)&(y<100)
    if ridge=='remaining_early':
        target=(d.times[rr]<29)&(np.abs(y+3.65*d.times[rr])<12)
    if ridge=='remaining_late':
        target=(d.times[rr]>52)&(np.abs(y-(270-3.1*d.times[rr]))<12)
    target_rows=np.unique(rr[target])
    print('target',len(target_rows),'groups',len(np.unique(d.group[target_rows])),flush=True)
    fig,axes=plt.subplots(2,1,figsize=(13,10),sharex=True)
    for ax in axes:
        ax.scatter(d.times[rr],y,s=9,c='.65',alpha=.65)
        ax.set_xlim(0,75);ax.set_ylim(-400,280);ax.set_yticks(np.arange(-400,281,50));ax.grid(alpha=.3)
        ax.set_ylabel('Calibrated Doppler (kHz)')
    axes[0].scatter(d.times[rr[target]],y[target],c='red',s=12,label='Broad visual ridge extraction')
    for ch in range(1,5):
        m=d.channel[rr]==ch
        axes[1].scatter(d.times[rr[m]],y[m],s=8,label=f'CH{ch}',alpha=.8)
    axes[0].legend();axes[1].legend();axes[1].set_xlabel('Receive time (s)')
    fig.suptitle('Scan B RX1 · early unassigned measurements and alias alternatives')
    fig.tight_layout();fig.savefig(out/f'{ridge}-extraction.png',dpi=160);plt.close(fig)
    allsat=np.arange(len(d.numbers))
    best=[None]*len(allsat)
    params=c.params.copy()
    common=float(np.mean(params[6+np.array(c.selected)]))
    rows=np.repeat(target_rows,len(allsat)); sats=np.tile(allsat,len(target_rows))
    for offset in np.arange(-20,20.001,.25):
        params[6:]=common+offset
        p,v,_=paired_prediction_jacobian(d,params,rows,sats)
        p=p.reshape(len(target_rows),-1)+(c.features@c.coeff)[target_rows,None]
        v=v.reshape(p.shape)
        residual=np.abs(circular_residual(d.measured[target_rows,None],p,c.prepared.alias_hz))
        residual=np.where(v,residual,np.inf)
        for j,n in enumerate(d.numbers):
            good=residual[:,j]<500
            count=len(np.unique(d.group[target_rows[good]]))
            med=float(np.median(residual[:,j]))
            rank=(count,-med)
            if best[j] is None or rank>tuple(best[j]['rank']):
                best[j]=dict(catalog_number=int(n),offset_s=float(offset),rank=rank,groups_within_500hz=count,
                             median_absolute_residual_hz=med,rows=target_rows[good].tolist())
    best.sort(key=lambda b:tuple(b['rank']),reverse=True)
    print('best',json.dumps([{k:v for k,v in b.items() if k!='rows'} for b in best[:12]]),flush=True)
    (out/f'{ridge}-screen.json').write_text(json.dumps(dict(scope=__doc__,target_rows=target_rows.tolist(),candidates=best),indent=2))


if __name__=='__main__':main()
