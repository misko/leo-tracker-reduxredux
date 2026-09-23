"""Render method comparisons from frozen numerical evidence; no IQ re-analysis."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parent
doc=json.loads((ROOT/'comparison.json').read_text())
pilot=json.loads((ROOT/'pilot-method-comparison.json').read_text())
inventory=json.loads((ROOT/'inventory.json').read_text())
existing=json.loads((ROOT/'existing-relative-phase.json').read_text())
rows=doc['visits'];good=[r for r in rows if r['state']=='replayed'];by={r['visit']:r for r in rows}
def wrap(v):return np.angle(np.exp(1j*np.asarray(v)))
def curveplot(ax,t,p,**kw):
    y=np.degrees(wrap(p));y[np.r_[False,abs(np.diff(y))>180]]=np.nan
    ax.plot(t,y,**kw)
def save(fig,name):fig.savefig(ROOT/name,dpi=170);plt.close(fig)

# The full scan and existing production-selected population, including failures.
fig,axes=plt.subplots(3,1,figsize=(13,9),sharex=True,layout='constrained')
visits=inventory['visits'];tt=[r['relative_time_s'] for r in visits]
for rx,color in [('0','#0072B2'),('1','#D55E00')]:
    axes[0].scatter(tt,[r['passing'][rx] for r in visits],s=7,alpha=.45,c=color,label=f'RX{rx} passing GLRT candidates')
times={r['visit_index']:r['relative_time_s'] for r in visits}
for state,color in [('supported','#009E73'),('insufficient_signal','#D55E00')]:
    subset=[r for r in existing if r['state']==state]
    axes[1].scatter([times[r['visit_index']] for r in subset],
                    [r['evidence'].get('tracked_coherence',np.nan) for r in subset],
                    c=color,s=26,label=f'{state}: {len(subset)}/64 selected')
axes[1].scatter([times[r['visit_index']] for r in existing],
                [r['evidence'].get('wrong_time_coherence',np.nan) for r in existing],
                marker='x',c='gray',s=14,label='Wrong-time control, where available')
for channel,color in [(1,'#0072B2'),(2,'#D55E00'),(3,'#009E73'),(4,'#CC79A7')]:
    sub=[r for r in visits if r['priority'] is not None and r['target']['channel']==channel]
    axes[2].scatter([r['relative_time_s'] for r in sub],[channel]*len(sub),c=color,s=9,alpha=.45,label=f'Channel {channel} paired visits')
for r in rows:axes[2].scatter(r['inventory']['relative_time_s'],r['inventory']['target']['channel'],marker='*',s=140,c='black',zorder=6)
axes[0].set_ylabel('Candidates / 20 ms probe');axes[1].set_ylabel('Held-band coherence');axes[2].set_ylabel('RF channel (upper edge)')
axes[2].set(yticks=[1,2,3,4],xlabel='Elapsed scan time (s)',xlim=(0,300))
for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8,loc='upper left')
fig.suptitle('scan-fw-1aa1d50103d97388 · pre-rotation, 2.5 MS/s, dual RX\n2,215 visits · 186 phase-blind paired visits · stars: eight frozen replay dwells',fontsize=14)
save(fig,'scan-phase-coverage.png')

# Same-gauge frequency-partition phase observations, independently per dwell.
fig,axes=plt.subplots(4,2,figsize=(13,12),sharex=True,sharey=True,layout='constrained')
for ax,r in zip(axes.flat,rows,strict=True):
    ch=r['inventory']['target']['channel']
    if r['state']!='replayed':
        ax.text(.5,.5,'ABSTAINED\nInsufficient disjoint frequency support',ha='center',va='center',transform=ax.transAxes,color='#b23b25')
        ax.set_title(f"Visit {r['visit']} · channel {ch}")
    else:
        rate=r['sample_rate_hz'];full=r['all_band_phase']['rows'];held=r['held_band_phase']['rows'];fits=r['curve_fits']
        t=np.array([p['center_sample']/rate*1000 for p in full]);a=np.array([p['training_band_phase_rad'] for p in full])
        ht=np.array([p['center_sample']/rate*1000 for p in held]);b=np.array([p['training_band_phase_rad']+p['held_band_residual_phase_rad'] for p in held])
        ax.scatter(t,np.degrees(wrap(a)),s=10,color='#009E73',label='A-band observed')
        ax.scatter(ht,np.degrees(wrap(b)),s=15,color='#CC79A7',marker='x',label='Later B-band check')
        curveplot(ax,np.array(fits['time_s'])*1000,fits['curves_rad']['linear'],c='#D55E00',ls='--',lw=1,label='Linear (A-fit)')
        curveplot(ax,np.array(fits['time_s'])*1000,fits['curves_rad'][fits['selected']],c='black',lw=1.7,label=f"A-selected {fits['selected']}")
        status='supported' if r['production_relative_phase']['supported'] else 'NOT supported'
        ax.set_title(f"Visit {r['visit']} · channel {ch} · {status}\nSpline / linear B RMS: {fits['B_validation'][fits['selected']]['B_rms_deg']:.1f}° / {fits['B_validation']['linear']['B_rms_deg']:.1f}°",fontsize=10)
    ax.axvline(60,c='gray',ls=':');ax.set(xlim=(0,120),ylim=(-185,185));ax.grid(alpha=.2)
axes[0,0].legend(fontsize=7,loc='lower left')
for ax in axes[-1]:ax.set_xlabel('Time within dwell (ms)')
for ax in axes[:,0]:ax.set_ylabel('Wrapped residual phase (degrees)')
fig.suptitle('Within-dwell phase fits on identical saved IQ\nCarrier and response fitted on first 60 ms; A selects the curve, later B checks it · no phase connection across retunes',fontsize=13)
save(fig,'phase-fit-comparison.png')

names=['principal','branch_lifted','offset_authority','shared_residual','refined_shared']
curve_names=['linear','quadratic','cubic','spline_0','spline_1','spline_4','spline_16']
coh=[];rms=[];prms=[]
for r in rows:
    if r['state']!='replayed':coh.append([np.nan]*6);rms.append([np.nan]*7);prms.append([np.nan]*5);continue
    h=r['held_band_phase']
    coh.append([h['forecast']['coherence'],r['guided']['absolute']['held_out']['coherence'],r['guided']['evolution']['held_out']['coherence'],r['original_response_tracking']['tracked']['coherence'],h['tracked']['coherence'],h['wrong_time']['coherence']])
    rms.append([r['curve_fits']['B_validation'][name]['B_rms_deg'] for name in curve_names])
    prms.append([next((p['held_rms_deg'] for p in pilot if p['visit']==r['visit'] and p['method']==name),None) for name in names])
fig,axes=plt.subplots(3,1,figsize=(14,13),layout='constrained')
labels=[f"{r['visit']} / ch{r['inventory']['target']['channel']}" for r in rows]
for ax,data,columns,title,maxval,cmap in zip(axes,[coh,rms,prms],
        [['Frozen normalized H','GLRT-guided absolute','GLRT-guided evolution','A tracker original H','A tracker normalized H','Wrong-time control'],curve_names,names],
        ['Later-time amplitude coherence (higher is better; masks differ between estimator families)',
         'Later B-band phase discrepancy for A-fitted curves (degrees; lower is better)',
         'Pilot versus frame-matched scalar phase: later RMS after training-only offset (degrees)'],[.15,130,180],['viridis','magma_r','magma_r'],strict=True):
    data=np.array(data,dtype=float);im=ax.imshow(data,aspect='auto',vmin=0,vmax=maxval,cmap=cmap)
    ax.set(xticks=np.arange(len(columns)),xticklabels=columns,yticks=np.arange(len(labels)),yticklabels=labels,title=title)
    for (i,j),v in np.ndenumerate(data):
        text='N/A' if not np.isfinite(v) else f'{v:.3f}' if maxval<1 else f'{v:.1f}'
        ax.text(j,i,text,ha='center',va='center',fontsize=9,color='white' if np.isfinite(v) and (v<maxval*.5 if cmap=='viridis' else v>maxval*.5) else 'black')
    fig.colorbar(im,ax=ax,shrink=.85)
fig.suptitle('Method checks · eight phase-blind-selected dwells\nPilot/scalar agreement is conditional on a common carrier and training offset; it is not geometric accuracy',fontsize=14)
save(fig,'phase-method-validation.png')

# Most strongly paired dwell, selected before inspecting phase results.
r=by[544];m=r['broadband']['model'];rate=r['sample_rate_hz'];prod=r['production_relative_phase'];fits=r['curve_fits']
fig,axes=plt.subplots(4,1,figsize=(12,12),sharex=True,layout='constrained')
t=np.array(fits['time_s'])*1000;a=np.unwrap([z['training_band_phase_rad'] for z in r['all_band_phase']['rows']])
axes[0].scatter(t,np.degrees(a),s=12,c='#009E73',label='A-band observed')
for name,color in [('linear','#D55E00'),('quadratic','#E69F00'),('cubic','#0072B2'),('spline_1','black')]:
    axes[0].plot(t,np.degrees(fits['curves_rad'][name]),label=name,color=color)
for name in names:
    pp=[p for p in r['pilot_variants'] if p['method']==name]
    axes[1].plot([p['time_s']*1000 for p in pp],[(p['relative_frequency_hz']-m['relative_cfo_hz'])/1000 for p in pp],'.-',label=name)
for name in names:
    pp=next(p for p in pilot if p['visit']==544 and p['method']==name)
    axes[2].plot([p['time_s']*1000 for p in pp['rows']],[p['aligned_discrepancy_deg'] for p in pp['rows']],'.-',label=f"{name}: {pp['held_rms_deg']:.1f}° later RMS")
axes[3].plot(np.array(prod['scalar_time_s'])*1000,prod['scalar_coherence'],color='black',label='Rolling scalar amplitude coherence')
hr=r['held_band_phase']['rows'];axes[3].plot([p['center_sample']/rate*1000 for p in hr],[p['held_band_coherence'] for p in hr],label='B-band block coherence',color='#CC79A7')
for ax in axes:ax.axvline(60,c='gray',ls=':');ax.grid(alpha=.2);ax.legend(fontsize=8,loc='upper left');ax.set_xlim(0,120)
axes[0].set_ylabel('Unwrapped residual phase (°)');axes[1].set_ylabel('Pilot minus broadband CFO (kHz)')
axes[1].set_yscale('symlog',linthresh=.05)
axes[1].set_ylim(-.06,150)
axes[1].set_yticks([-.05,0,.05,1,10,100],labels=['−0.05','0','0.05','1','10','100'])
axes[1].set_ylabel('Pilot − broadband CFO (kHz)\nsymlog; linear within ±0.05 kHz')
axes[2].set_ylabel('Pilot − matched scalar (°)');axes[3].set_ylabel('Amplitude coherence');axes[3].set_xlabel('Time within visit 544 (ms)')
fig.suptitle('Visit 544 · strongest paired GLRT margin · channel 3 upper\nPilot frequency-branch handling and flexible phase fits materially change the result',fontsize=14)
save(fig,'visit-544-method-detail.png')

fig,axes=plt.subplots(2,2,figsize=(13,7),sharex=True,sharey=True,layout='constrained')
for col,index in enumerate((544,1464)):
    ex=by[index]['sample_excerpt']
    for row,(key,label) in enumerate([('raw_phase_rad','Raw RX1 × conj(RX0)'),('corrected_phase_rad','Carrier/delay/common-band corrected')]):
        axes[row,col].scatter(np.array(ex['time_s'])*1000,np.degrees(ex[key]),s=.5,alpha=.35)
        axes[row,col].set(title=f'Visit {index} · {label}',ylim=(-180,180),xlim=(60,62),ylabel='Sample phase (°)',xlabel='Time within dwell (ms)')
fig.suptitle('Every sample in the same fixed 2 ms excerpt · 5,000 samples per receiver\nLeft: supported phase tracking; right: near-null control-level coherence · sample scatter alone does not qualify tracking',fontsize=13)
save(fig,'per-sample-phase-comparison.png')

dd=json.loads((ROOT/'double-differences.json').read_text())
fig,axes=plt.subplots(1,3,figsize=(13,4),layout='constrained')
for ax,record in zip(axes,dd,strict=True):
    h=record['hypotheses'][0];phase=np.degrees(h['wrapped_high_minus_low_rad']);se=np.degrees(h['standard_error_rad'])
    ax.errorbar([0],[phase],yerr=[se],fmt='o',capsize=6,color='#0072B2')
    other=(phase+180+180)%360-180;ax.scatter([0],[other],facecolors='none',edgecolors='#D55E00',s=65,label='Unresolved π branch')
    ax.set(xlim=(-1,1),ylim=(-180,180),xticks=[],ylabel='High − low receiver phase (°)',
           title=f"Visit {record['visit_index']} · {h['common_session_time_s']:.3f} s\n{phase:.1f}° ± {se:.1f}° conditional SE")
    ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Three local two-source double differences; no connected phase track\nAll use asynchronous-center correction; zero directly shared frames; π ambiguity unresolved',fontsize=13)
save(fig,'two-source-double-differences.png')

# Constant phase enumeration and scalar LS are the same local objective.
r=by[544];prod=r['production_relative_phase'];t=np.asarray(prod['scalar_time_s'])*1000
p=np.asarray(prod['scalar_phase_rad']);rho=np.asarray(prod['scalar_coherence']);grid=np.linspace(-180,180,361)
fig,axes=plt.subplots(2,1,figsize=(12,6),sharex=True,layout='constrained')
heat=rho[None,:]*np.cos(np.radians(grid[:,None])-p[None,:])
im=axes[0].pcolormesh(t,grid,heat,shading='auto',cmap='coolwarm',vmin=-.25,vmax=.25)
axes[0].scatter(t,np.degrees(p),c='black',s=2,label='Scalar complex-LS phase / grid maximum')
axes[0].legend(fontsize=8);fig.colorbar(im,ax=axes[0],label='Signed coherence')
axes[0].set_ylabel('Trial phase (degrees)')
axes[1].plot(t,np.sqrt(np.maximum(0,1-rho**2)),c='black')
axes[1].set(xlabel='Time within visit 544 (ms)',ylabel='Minimum normalized\nscalar prediction error')
for ax in axes:ax.axvline(60,c='gray',ls=':');ax.grid(alpha=.2);ax.set_xlim(0,120)
fig.suptitle('Visit 544 · constant-phase enumeration versus scalar least squares\n0.5 ms windows, 0.2 ms stride · descriptive common-band fit; overlapping windows are correlated',fontsize=13)
save(fig,'scalar-phase-likelihood.png')
print('Rendered seven comparison PNGs')
