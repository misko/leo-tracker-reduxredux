"""Plot saved zero-time fits; circle area encodes total track observations."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main():
    data=json.loads((HERE/'two_zero_results.json').read_text())
    scans=sorted(data['scans'],key=lambda s:s['utc'])
    selected=[r for s in scans for r in s['rows'] if r['site'] in ('reno','sacramento') and r['fits']['2'] is not None]
    values=[r['fits'][d]['evaluation_rms_hz'] for r in selected for d in ('0','2')]
    lo=min(values)*.65;hi=max(values)*1.5
    fig,axes=plt.subplots(2,2,figsize=(11,10),sharex=True,sharey=True)
    fig.subplots_adjust(left=.09,right=.97,bottom=.18,top=.86,wspace=.15,hspace=.23)
    colors={'reno':'#ce6525','sacramento':'#2369ad'}
    scale=2.5
    for row,scan in enumerate(scans):
        for col,site in enumerate(('reno','sacramento')):
            ax=axes[row,col]
            rr=[r for r in scan['rows'] if r['site']==site and r['fits']['2'] is not None]
            # Draw larger circles first so smaller observations remain visible.
            rr.sort(key=lambda r:r['training_count']+len(r['fits']['0']['evaluation_residual_hz']),reverse=True)
            n=np.array([r['training_count']+len(r['fits']['0']['evaluation_residual_hz']) for r in rr])
            assert np.all(n>3) and all(r['tau_s']==0 for r in rr)
            ax.scatter([r['fits']['0']['evaluation_rms_hz'] for r in rr],
                [r['fits']['2']['evaluation_rms_hz'] for r in rr],
                s=scale*n,marker='o',color=colors[site],alpha=.55,edgecolors=colors[site],linewidths=.5)
            ax.plot([lo,hi],[lo,hi],ls=':',color='gray',lw=1.3,zorder=0)
            ax.set(xscale='log',yscale='log',xlim=(lo,hi),ylim=(lo,hi),
                title=f"{scan['utc']} UTC — {site.title()}\n{len(rr)}/{scan['tracks']} tracks · location error {scan['location_errors_m'][site]/1000:.1f} km")
            ax.set_aspect('equal',adjustable='box')
            ax.grid(alpha=.2)
            if row==1:ax.set_xlabel('Constant residual RMS (Hz)')
            if col==0:ax.set_ylabel('Quadratic residual RMS (Hz)')
    counts=[r['training_count']+len(r['fits']['0']['evaluation_residual_hz']) for r in selected]
    legend_counts=sorted(set(int(v) for v in np.quantile(counts,[0,.5,1])))
    handles=[axes[0,0].scatter([],[],s=scale*n,color='gray',alpha=.55,label=f'{n} observations') for n in legend_counts]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.035),ncol=len(handles),
        title='Circle area ∝ total observations (training + evaluation)',frameon=False,labelspacing=1.2)
    fig.suptitle('Zero timing offset • constant versus quadratic residual RMS\nBelow diagonal = quadratic improves evaluation RMS',y=.965,fontsize=15)
    fig.text(.5,.012,'Training-only fits; fixed satellite IDs. Two 10:30 tracks lack enough training points for quadratic fitting.',ha='center',fontsize=9)
    fig.savefig(HERE/'two_zero_scatter.png',dpi=180)
    fig.savefig(HERE/'two_zero_scatter.pdf')
    plt.close(fig)
    print('Plotted',len(selected),'track/site points; observation count range',min(counts),max(counts))


if __name__=='__main__':main()
