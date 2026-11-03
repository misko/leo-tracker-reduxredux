"""Static orbit-free paired-clock diagnostic from saved exact top-one rows."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
def main():
    data=json.loads((HERE/'paired_topone.json').read_text())
    for case,cohorts in data['cases'].items():
        cohort=cohorts['100ns'];rows=cohort['rows'];t=np.array([r['time_s'] for r in rows]);raw=np.array([r['difference_hz'] for r in rows]);base=np.array([r['baseline_difference_hz'] for r in rows]);full=base+np.array([r['selected_rx_nuisance_difference_hz'] for r in rows]);res=np.array([r['full_fit_residual_hz'] for r in rows]);margin=np.array([min(r['margin0'],r['margin1']) for r in rows]);ch=np.array([r['channel'] for r in rows]);model=cohort['models']['full_fit_residual_hz']['1'];beta=np.array(model['coefficients']);z=(t-model['time_center_s'])/model['time_scale_s'];slope=beta[-1]/model['time_scale_s']
        fig,axes=plt.subplots(3,1,figsize=(10,9),sharex=True,constrained_layout=True)
        order=np.argsort(t)
        sc=axes[0].scatter(t,raw,c=margin,cmap='viridis',vmin=0,vmax=1,s=18,label='Observed RX1 − RX0 CFO (circular)')
        axes[0].plot(t[order],base[order],color='orange',lw=1.6,label='Frozen calibration RX difference')
        axes[0].plot(t[order],full[order],color='red',lw=1.6,label='Calibration + selected fitted RX nuisance')
        axes[0].set_ylabel('Differential CFO (Hz)');axes[0].legend(fontsize=8);fig.colorbar(sc,ax=axes[0],label='Weaker fractional margin')
        colors=plt.get_cmap('tab10')
        for i,c in enumerate(model['channel_order']):
            mask=ch==c;axes[1].scatter(t[mask],res[mask],s=15,color=colors(i),alpha=.7,label=f'Channel {c}')
            axes[1].plot(t[mask][np.argsort(t[mask])],(beta[i]+beta[-1]*z[mask])[np.argsort(t[mask])],color=colors(i),lw=1.4)
        axes[1].axhline(0,color='black',lw=.7);axes[1].set_ylabel('Observed − selected model (Hz)');axes[1].legend(fontsize=8,ncol=4)
        axes[1].set_title(f'Independent Huber100Hz trend, separate channel intercepts: {slope:+.3f} Hz/s',fontsize=10)
        axes[2].scatter(t,margin,s=15,c=ch,cmap='tab10');axes[2].set_ylim(0,1);axes[2].set_ylabel('Weaker fractional margin');axes[2].set_xlabel('Acquisition epoch seconds after capture first sample')
        for ax in axes:ax.grid(alpha=.2)
        fig.suptitle(f'{"12:39" if case=="1939" else "14:39"} PDT: {len(rows)} exact retained RX pairs, acquisition epoch difference ≤100 ns\nSame visit/probe/RF; no CFO filter. Pilot phase agreement is not decoded satellite identity.',fontsize=11)
        fig.savefig(HERE/f'paired-clock-{case}.png',dpi=170);fig.savefig(HERE/f'paired-clock-{case}.svg');plt.close(fig)
if __name__=='__main__':main()
