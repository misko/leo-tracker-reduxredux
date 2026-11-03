"""Paired catalogue/model and independent-family attribution plots."""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from investigate import read,MODELS
from render import ranked


def main(out):
    for row in read(out/'targets.json'):
        d=read(out/'cases'/row['case']/(row['fragment_id']+'.json'));t=np.array(d['times_s']);best=ranked(d)[0]
        names=sorted(set([r['norad'] for r in ranked(d)[:3]]+[r['norad'] for r in ranked(d,'later')[:3]]));models=list(MODELS)
        fig,axs=plt.subplots(2,2,figsize=(14,10),layout='constrained')
        for ax,reg in zip(axs[0],['causal','later']):
            matrix=np.full((len(names),len(models)),np.nan);rm=matrix.copy()
            for i,n in enumerate(names):
                for j,m in enumerate(models):
                    r=next((r for r in d['fits'] if r['regime']==reg and r['arm']=='fitted_c' and r['norad']==n and r['model']==m),None)
                    if r:matrix[i,j]=r['cost'];rm[i,j]=r['rms_hz']
            matrix-=np.nanmin(matrix,axis=0);cmap=plt.colormaps['magma_r'].copy();cmap.set_bad('.75')
            im=ax.imshow(np.minimum(matrix,200),vmin=0,vmax=200,cmap=cmap,aspect='auto');fig.colorbar(im,ax=ax,label='Score above best per column; cap 200')
            ax.set_yticks(range(len(names)),names);ax.set_xticks(range(4),['Phase/offset','Small rate','Wider rate','Affine control'],rotation=15)
            for i in range(len(names)):
                for j in range(4):ax.text(j,i,'missing TLE' if np.isnan(rm[i,j]) else f'{rm[i,j]:.0f} Hz',ha='center',va='center',fontsize=8,color='white' if matrix[i,j]>90 else 'black')
            ax.set(title=reg+' catalogue',ylabel='NORAD')
        ax=axs[1,0];shared=next(r for r in read(out/'cases'/row['case']/'shared_competitors.json') if r['source']['fragment_id']==row['fragment_id'])
        rr=[r for r in shared['predictions'] if r['arm']=='fitted_c' and r['status']=='independent_shared_prediction']
        if rr:
            ax.bar(range(len(rr)),[r['rms_hz'] for r in rr],color='#176bbb');ax.set_xticks(range(len(rr)),[str(r['norad']) for r in rr]);ax.set_yscale('log')
            for i,r in enumerate(rr):ax.text(i,r['rms_hz']*1.1,f'{r["rms_hz"]:.1f} Hz',ha='center',fontsize=9)
        else:ax.text(.5,.5,'No independently calibrated family\nfor these finalists',ha='center',transform=ax.transAxes)
        ax.set(title='Independent shared model → target (no target phase/rate fit)',ylabel='RMS (Hz)',xlabel='NORAD')
        ax=axs[1,1];attrib=d['receiver_family_attribution']
        if attrib:
            for rx in [1,2]:
                for same,marker in [(True,'*'),(False,'o')]:
                    rows=[r for r in attrib if r['receiver']==rx and r['same_family']==same]
                    ax.scatter([r['channel'] for r in rows],[r['rate_hz_s'] for r in rows],s=80 if same else 25,marker=marker,label=f'RX{rx}, '+('same satellite' if same else 'other satellites'))
            ax.axhline(best['rate_hz_s'],color='#b40040',ls='--',label='Target extra rate')
            ax.axhline(0,color='k',lw=.6);ax.legend(fontsize=7)
        else:ax.text(.5,.5,'No overlapping active support',ha='center',transform=ax.transAxes)
        ax.set(title='Residual-rate attribution on overlapping independent tracks',xlabel='Channel',ylabel='Residual fitted rate (Hz/s)')
        name=row['case']+'-'+row['key'].split('-RF')[0].replace('SCAN-','')
        fig.suptitle(name+' — competitors and shared support');fig.savefig(out/'figures'/(name+'-support.png'),dpi=135);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);main(p.parse_args().output)
