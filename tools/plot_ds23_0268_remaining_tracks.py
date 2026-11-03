"""Scientific orbit overlays with explicit, unchanged association ownership."""

import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from investigate_ds23_0268_remaining_tracks import OUT,CASE,ARMS,load,family_frequency,corrected_observation
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import read,write
from leo.analysis.research.retained_track_likelihood import PERIOD,projected_receiver_basis,profile


def wrapped_residual(values,prediction):
    return (np.asarray(values)-prediction+PERIOD/2)%PERIOD-PERIOD/2


def alias_lines(prediction,lower,upper):
    """All native alias copies intersecting the plotted measured-CFO range."""
    prediction=np.asarray(prediction)
    first=int(np.ceil((lower-prediction.max())/PERIOD));last=int(np.floor((upper-prediction.min())/PERIOD))
    return [np.where((line>=lower)&(line<=upper),line,np.nan)
            for k in range(first,last+1) for line in (prediction+k*PERIOD,)]


def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=170,bbox_inches='tight');fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight');plt.close(fig)


def orbit_overlays():
    scan,base,saved,coverage,problems=load();obs=read(SOURCE/CASE/'observations.json');post=dict(np.load(OUT/'postscan_bank.npz'))
    j=int(np.flatnonzero(scan.norads==53923)[0]);grid=np.linspace(200,300,501);metrics=[]
    colors=dict(satellite='#16833f',other='#267dc0',unknown='#e44a65')
    for arm,(p,x) in problems.items():
        state=p.state(x);accepted=coverage['arms'][arm]['accepted_rows'];owned=set(coverage['arms'][arm]['associated_observation_ids'])
        family_ids=set()
        for row in accepted:
            if row['norad']==53923:
                t=next(t for t in scan.tracks if t['key']==row['component'])
                family_ids.update(row.get('observation_ids',t['observation_ids']))
        fitted,_=family_frequency(p,x,j,times=grid)
        nominal,_=family_frequency(p,x,j,corrected=False,times=grid)
        future,_=family_frequency(p,x,j,bank=post,corrected=False,times=grid)
        for rx in (1,2):
            fig,axes=plt.subplots(4,4,figsize=(22,14),sharex=True)
            for ch in range(1,9):
                r=(ch-1)%4;c=0 if ch<=4 else 2;top,res=axes[r,c:c+2]
                points=[o for o in obs if o['receiver']==rx and o['channel']==ch and 200<=o['time_s']<=300]
                if not points:continue
                times=np.asarray([o['time_s'] for o in points]);values=np.asarray([o['measured_cfo_hz'] for o in points]);rf=points[0]['actual_rf_hz'];q=rf/11.5e9
                virtual=dict(times=grid,receiver=rx,channel=ch,rf_hz=rf)
                calibration=p.scan.hardware(virtual,state['beta'])+q*projected_receiver_basis(grid)@state['smooth'][rx-1]
                prediction=q*fitted+calibration
                lower=values.min()-10000;upper=values.max()+10000
                for freq,color,style in ((nominal,'#e29b21','--'),(future,'#9646ad',':'),(fitted,'black','-')):
                    for line in alias_lines(q*freq+calibration,lower,upper):
                        top.plot(grid,line/1000,color=color,ls=style,lw=1.15)
                for status in ('other','unknown','satellite'):
                    mask=np.asarray([('satellite' if o['observation_id'] in family_ids else 'other' if o['observation_id'] in owned else 'unknown')==status for o in points])
                    top.scatter(times[mask],values[mask]/1000,color=colors[status],s=12,alpha=.75,zorder=3)
                    delta=wrapped_residual(values[mask],np.interp(times[mask],grid,prediction))
                    res.scatter(times[mask],delta,color=colors[status],s=12,alpha=.75)
                    metrics.append(dict(arm=arm,receiver=rx,channel=ch,status=status,points=int(mask.sum()),
                        residuals_outside_3kHz=int(np.sum(abs(delta)>3000))))
                top.set_title(f'CH{ch} · all GLRT + 53923');res.set_title(f'CH{ch} · residual to current 53923')
                top.set_ylabel('Native CFO (kHz)');top.set_ylim(lower/1000,upper/1000)
                res.set_ylabel('Wrapped residual (Hz)');res.set_ylim(-3000,3000)
                for a in (top,res):a.grid(alpha=.15);a.set_xlim(200,300)
                res.axhline(0,color='black',lw=.7)
            handles=[Line2D([],[],marker='o',ls='',color=colors[k],label=label) for k,label in
                (('satellite','Associated with 53923'),('other','Associated with another satellite'),('unknown','Unassociated'))]
            handles += [Line2D([],[],color=color,ls=style,label=label) for color,style,label in
                (('black','-','Current causal fit: shared phase + orbit modes + receiver calibration'),
                 ('#e29b21','--','Causal nominal orbit: same fitted phase/calibration'),
                 ('#9646ad',':','Post-scan orbit: same phase/calibration, diagnostic only'))]
            fig.legend(handles=handles,loc='lower center',ncol=3,fontsize=10)
            fig.suptitle(f'DS23-0268 · RX{rx} · 53923 / STARLINK-5004 · {arm}\n'
                '200–300 s · all alias branches · current receiver/band calibration; no per-track constant fitted to overlay\n'
                'Residual panels show ±3 kHz; unrelated points outside that range are clipped',fontsize=15)
            for a in axes[-1]:a.set_xlabel('Time from scan start (s)')
            fig.tight_layout(rect=(0,.075,1,.91));save(fig,f'53923_all_GLRT_RX{rx}_{arm}')
    write(OUT/'orbit_overlay_receipt.json',dict(rows=metrics,
        all_native_winning_GLRT_shown_in_CFO_panels=True,association_labels_unchanged=True,
        residual_alias_period_hz=PERIOD,per_track_constants_not_removed_from_overlays=True,
        causal_position_hardware_phase_held_fixed_for_postscan_curve=True))


def screen_figures():
    scan,base,saved,coverage,problems=load();causal=read(OUT/'causal_refined.json');future=read(OUT/'postscan_refined.json')
    target='DS23-0268-RX1-CH7-T000-RF12440312500.000000';i=next(i for i,t in enumerate(scan.tracks) if t['key']==target);t=scan.tracks[i]
    fig,axes=plt.subplots(3,1,figsize=(14,11),sharex=True)
    for arm,style in (('c0','-'),('fitted_c','--')):
        p,x=problems[arm];corrected=corrected_observation(p,x,i)
        for kind,document,color,norad in (('causal',causal,'#e08a13',64333),('postscan',future,'#8046aa',64333),
                                        ('postscan alternative',future,'#16833f',69468)):
            row=next(r for r in document['arms'][arm] if r['component']==target)
            best=next(r['best'] for r in row['refined'] if r['best']['norad']==norad)
            native=t['values']-np.asarray(best['residual_hz'])
            axes[0].plot(t['times'],native/1000,ls=style,color=color,label=f"{kind} {arm}: {best['norad']}, phase {best['phase_s']:.2f}s")
            axes[1].plot(t['times'],best['residual_hz'],marker='.',ls=style,color=color,ms=4,
                label=f"{kind} {arm}: RMS {best['rms_hz']:.1f}Hz; {'passes local screen' if best['passing'] else 'fails local screen'}")
        k=next(k for k,r in enumerate(p.rows) if r['component']==target);sl=p.slices[k];r=p.calculate(x)['conditional_residual_hz'][sl]
        axes[2].plot(t['times'],r,marker='.',ls=style,color='#d83252' if arm=='c0' else '#257c85',label=f'{arm}: current shared-family conditional residual')
    axes[0].scatter(t['times'],t['values']/1000,color='#e44a65',s=20,zorder=5,label='60 unassociated GLRT points')
    axes[0].set_ylabel('CFO on graph branch (kHz)');axes[1].set_ylabel('Own-phase residual (Hz)');axes[2].set_ylabel('Shared-family residual (Hz)')
    for ax in axes:ax.grid(alpha=.18);ax.legend(fontsize=8)
    for ax in axes[1:]:ax.axhline(0,color='black',lw=.7)
    axes[-1].set_xlabel('Time from scan start (s)')
    fig.suptitle('RX1 CH7 T000 · 120.6–177.3 s · one graph polynomial\n'
        'Independent phase searches are diagnostics; current family constraints remain shared',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.94));save(fig,'CH7_150s_orbits_and_residuals')

    ranking=read(OUT/'inventory.json')['ranking'];curved=[r for r in ranking if r['curved'] and r['unassociated_points']==r['points']]
    fig,axes=plt.subplots(len(curved),2,figsize=(16,3*len(curved)),squeeze=False)
    for axrow,row in zip(axes,curved,strict=True):
        t=scan.tracks[row['track_index']]
        axrow[0].scatter(t['times'],t['values']/1000,color='#e44a65',s=13,label='Unassociated GLRT')
        for document,label,color in ((causal,'Causal','#e08a13'),(future,'Post-scan','#8046aa')):
            r=next(r for r in document['arms']['c0'] if r['component']==row['component']);b=r['refined'][0]['best']
            axrow[0].plot(t['times'],(t['values']-np.asarray(b['residual_hz']))/1000,color=color,lw=1,
                label=f"{label} {b['norad']}: {b['rms_hz']:.0f}Hz {'PASS' if b['passing'] else 'FAIL'}")
            axrow[1].plot(t['times'],b['residual_hz'],'.-',color=color,ms=3,lw=.6,label=label)
        axrow[0].set_title(row['component'].split('-RF')[0].replace(CASE+'-','')+f" · {row['points']} points")
        axrow[0].set_ylabel('CFO (kHz)');axrow[1].set_ylabel('Residual (Hz)');axrow[1].axhline(0,color='black',lw=.7)
        for ax in axrow:ax.grid(alpha=.18);ax.legend(fontsize=8);ax.set_xlabel('Scan time (s)')
    fig.suptitle('All wholly unassociated curved graph tracks · independent full-catalogue phase probes\n'
        'Frozen current RF endpoint/calibration; no new orbit modes; local PASS does not establish identity',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.96));save(fig,'remaining_curved_track_gallery')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('orbit','screens'),required=True)
    stage=parser.parse_args().stage
    orbit_overlays() if stage=='orbit' else screen_figures()
