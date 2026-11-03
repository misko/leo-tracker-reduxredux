"""Residual check for the two previously questioned N12 satellite tracks."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from satellite_drift_localization import OUT,MODES,load,SatelliteDriftObjective


def main():
    root=OUT/'polished';scan='N12';numbers=(62866,62868)
    data,meta,_=load(scan)
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharey='row',sharex='row')
    summary=[]
    colors=['#0072b2','#e69f00','#009e73','#cc79a7']
    for col,mode in enumerate(MODES):
        r=json.loads((root/f'{scan}-fitted-c-{mode}.json').read_text())
        obj=SatelliteDriftObjective(data,meta['rf_center_hz'],'fitted-c',mode)
        v=np.asarray(r['best']['vector']);obj.evaluate(v)
        prediction,_=obj.base.predict(v[:obj.size])
        prediction+=obj.likelihood.correction()
        alias=obj.likelihood.alias_hz
        residual=(data.measured[:,None]-prediction+alias/2)%alias-alias/2
        for row,number in enumerate(numbers):
            j=int(np.flatnonzero(data.numbers==number)[0]);keep=data.owners==number
            ax=axes[row,col]
            for lane,channel in enumerate(sorted(np.unique(data.channel))):
                for rx,marker in [(0,'o'),(1,'^')]:
                    mask=keep&(data.channel==channel)&(data.receiver==rx)
                    ax.scatter(data.times[mask],residual[mask,j],s=18,c=colors[lane],marker=marker,alpha=.8)
            rms=float(np.sqrt(np.mean(residual[keep,j]**2)))
            slope=float(v[obj.size+j])
            ax.axhline(0,c='.4',lw=.8);ax.grid(alpha=.17)
            ax.set_title(f'{number} · '+('Original model' if col==0 else 'Shared satellite drift')+
                f'\n{sum(keep)} windows · RMS {rms:.1f} Hz · added slope {slope:+.2f} Hz/s')
            ax.set_xlabel('Receive time (s)')
            if col==0:ax.set_ylabel('Observed − fitted prediction (Hz)')
            summary.append(dict(satellite=number,mode=mode,windows=int(sum(keep)),
                residual_rms_hz=rms,drift_hz_s=slope,position_error_m=r['distance_m'],converged=r['converged']))
    from matplotlib.lines import Line2D
    handles=[Line2D([],[],color=c,marker='o',ls='none',label=f'CH{i+1}') for i,c in enumerate(colors)]
    handles += [Line2D([],[],color='.4',marker=m,ls='none',label=f'RX{i}') for i,m in enumerate(['o','^'])]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.92),ncol=6,frameon=False)
    fig.suptitle('N12 · same GLRT windows, with and without a shared per-satellite drift',fontsize=15)
    fig.text(.5,.015,'Each column uses its own independently fitted position and other nuisance parameters. No satellite/window removals.\n'
        'Shared slope prior: N(0, 2² Hz²/s²) at 11.085 GHz, scaled to actual RF. In-sample, not proof of transmitter drift or identity.\n'
        '62868 switches receiver between the early and late segments: time and receiver effects are confounded here.',
        ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.10,1,.87));fig.savefig(root/'N12-residual-comparison.png',dpi=165);plt.close(fig)
    (root/'N12-residual-comparison.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
