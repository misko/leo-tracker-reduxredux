"""Static paired scientific figures; not an inference or classification step."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'nuisance_results.json').read_text())
colors={'reference':'#1769a6','reno':'#c46117'}
labels={'reference':'Known receiver location','reno':'Wrong Reno location (706.8 km error)'}
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.titlesize':12,'figure.facecolor':'white'})


def ecdf(ax,key,scale=1,absolute=False):
    for branch,rows in data['branches'].items():
        x=np.array([r['base'][key] for r in rows])*scale
        if absolute: x=np.abs(x)
        x=np.sort(x)
        ax.step(np.r_[x[0],x],np.r_[0,np.arange(1,len(x)+1)/len(x)*100],where='post',
                color=colors[branch],ls='-' if branch=='reference' else '--',lw=2,label=labels[branch])
    ax.set_ylabel('Tracks at or below value (%)')
    ax.set_ylim(0,102)
    ax.grid(alpha=.18)


fig,axes=plt.subplots(2,2,figsize=(12,8.3))
for branch,rows in data['branches'].items():
    values=np.array([r['base']['tau_s'] for r in rows])
    counts=np.array([np.count_nonzero(values==tau) for tau in range(-5,6)])
    offset=-.19 if branch=='reference' else .19
    axes[0,0].bar(np.arange(-5,6)+offset,counts,width=.36,color=colors[branch],label=labels[branch],
                  hatch=None if branch=='reference' else '//',alpha=.9)
axes[0,0].set(title='Timing correction: current 1-second grid',xlabel='Fitted τ (seconds)',ylabel='Track count',xticks=np.arange(-5,6))
axes[0,0].text(.03,.96,'At ±5 s: reference 11/46; Reno 9/46',transform=axes[0,0].transAxes,va='top',fontsize=10)
axes[0,0].set_ylim(0,18)
axes[0,0].grid(axis='y',alpha=.18)
ecdf(axes[0,1],'offset_hz',scale=.001)
axes[0,1].set(title='Constant frequency offset — not drift',xlabel='Fitted offset b (kHz)')
ecdf(axes[1,0],'residual_slope_hz_per_s',absolute=True)
axes[1,0].set(title='Remaining linear trend after Doppler + offset fit',xlabel='|Residual slope| (Hz/s; training-only fit)',xscale='symlog')
axes[1,0].set_xlim(left=0)
ecdf(axes[1,1],'score_rms_hz')
axes[1,1].set(title='Residual error on original evaluation observations',xlabel='Evaluation RMS (Hz)',xscale='log')
handles,labs=axes[0,0].get_legend_handles_labels()
fig.legend(handles,labs,loc='upper center',bbox_to_anchor=(.5,.93),ncol=2,frameon=False)
fig.suptitle('Nuisance-fit distributions • 12:50 UTC scan • same 46 tracks',y=.975,fontsize=15)
fig.text(.5,.018,'Each track has equal weight. Different frozen satellite IDs at each location. Reference IDs are model fits, not decoded truth.',ha='center',fontsize=10)
fig.subplots_adjust(top=.86,bottom=.11,hspace=.38,wspace=.28)
fig.savefig(HERE/'nuisance_distributions.png',dpi=170)
plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(12,4.6))
for ax,row in zip(axes,data['branches']['reference'][:2]):
    p=row['profile']
    ax.axvspan(-5,5,color='#dddddd',alpha=.7,label='Current permitted range')
    ax.plot(p['tau_s'],p['train_rms_hz'],color='#1769a6',lw=2,label='Training RMS (selects τ)')
    ax.plot(p['tau_s'],p['score_rms_hz'],color='#7b4297',lw=2,ls='--',label='Evaluation RMS')
    for arm,marker in [('base','s'),('expanded','o')]:
        r=row[arm]
        ax.scatter(r['tau_s'],r['train_rms_hz'],color='#1769a6',marker=marker,s=55,zorder=5)
    ax.set(title=f"{row['span_s']:.1f} s track · {row['track_id'][7:15]} · satellite {row['satellite_id']}",xlabel='Orbit prediction time correction τ (s)',ylabel='Frequency residual RMS (Hz)',yscale='log',xlim=(-30,30))
    ax.grid(alpha=.18)
    ax.text(.97,.06,f"Train-selected τ: −5 → {row['expanded']['tau_s']:.0f} s\nEvaluation RMS: {row['base']['score_rms_hz']:.0f} → {row['expanded']['score_rms_hz']:.0f} Hz",transform=ax.transAxes,ha='right',va='bottom',fontsize=10)
handles,labs=axes[0].get_legend_handles_labels()
fig.legend(handles,labs,loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,.01))
fig.suptitle('The two longest reference-location fits were clipped by the ±5 s limit',fontsize=14)
fig.subplots_adjust(top=.83,bottom=.22,wspace=.25)
fig.savefig(HERE/'long_track_timing_profiles.png',dpi=170)
plt.close(fig)

summary={}
for branch,rows in data['branches'].items():
    s={'tracks':len(rows),'boundary_count':sum(r['base']['boundary'] for r in rows),
       'expanded_outside_original_range':sum(abs(r['expanded']['tau_s'])>5 for r in rows),
       'expanded_boundary_count':sum(r['expanded']['boundary'] for r in rows)}
    for key in ['tau_s','offset_hz','residual_slope_hz_per_s','residual_drift_over_span_hz','score_rms_hz']:
        values=np.array([r['base'][key] for r in rows])
        s[key]={'signed_p10_median_p90':np.percentile(values,[10,50,90]).tolist(),
                'absolute_p10_median_p90':np.percentile(np.abs(values),[10,50,90]).tolist()}
    summary[branch]=s
(HERE/'nuisance_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
