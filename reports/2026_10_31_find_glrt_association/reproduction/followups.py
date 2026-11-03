"""Targeted diagnostic follow-ups selected after the blinded catalogue screen."""
import argparse
from pathlib import Path
import numpy as np
from sgp4.api import Satrec
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from investigate import read,write,exact,MODELS,ARMS,polynomial_audit
from analyze_dsx01_fixed_site import ecef_states
from leo.sky.propagation import ElementSetCatalogue


def main(out):
    archive=read(out/'causal_finalist_archive_audit.json')['scans'];rows=read(out/'targets.json');results=[]
    for case,norad in [('DS26-0068',58538),('DS26-0062',67821),('DS26-0134',59642)]:
        row=next(r for r in rows if r['case']==case);d=read(out/'cases'/case/(row['fragment_id']+'.json'));receipt=read(out/'cases'/case/'receipt.json');source=archive[case][str(norad)]['latest_past_within_14d_archive'];t=np.array(d['times_s']);y=np.array(d['values_hz']);q=row['rf_hz']/11.5e9
        sat=Satrec.twoline2rv(*source['lines']);cat=ElementSetCatalogue((str(norad),),(norad,),(sat,));grid=np.arange(-125.,426.)
        pos,vel,ok=ecef_states(cat,receipt['scan_receipt']['origin_utc_ns'],grid);assert ok.all()
        bank=dict(time_s=grid,position_km=pos,velocity_km_s=vel);fits=[]
        for arm in ARMS:
            for bound in (15.,120.):
                for model in MODELS:
                    r=exact(bank,0,norad,t,np.array(d['corrected_hz'][arm]),receipt['positions'][arm],q,model,phase_limit=bound)
                    fits.append(dict(arm=arm,phase_limit_s=bound,**r))
        age=(receipt['scan_receipt']['cutoff_utc_ns']-source['epoch_utc_ns'])/3600e9
        r=dict(case=case,norad=norad,causal_source=source,age_hours=age,eligible_original_48h=archive[case][str(norad)]['eligible_48h'] is not None,fits=fits,protocol='post-screen targeted diagnosis, not a blind expanded-catalogue validation; same frozen radio and published position; Gaussian phase prior sigma 5 s remains penalized')
        results.append(r)
        fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
        for arm,color in [('c0','#176bbb'),('fitted_c','#e78618')]:
            for bound,style in [(15.,'--'),(120.,'-')]:
                fit=next(f for f in fits if f['arm']==arm and f['phase_limit_s']==bound and f['model']=='phase_small_rate')
                axes[0,0].plot(t,(y-np.array(fit['residual_hz']))/1000,ls=style,c=color,label=f'{arm}, ±{bound:g}s, RMS {fit["rms_hz"]:.1f} Hz')
                axes[0,1].plot(t,fit['residual_hz'],ls=style,c=color,label=f'{arm}, ±{bound:g}s')
        axes[0,0].scatter(t,y/1000,s=12,c='#b40040',label='Target native points (alias lifted)');axes[0,0].set(xlabel='Time (s)',ylabel='CFO (kHz)');axes[0,0].legend(fontsize=7)
        axes[0,1].axhline(0,c='k',lw=.6);axes[0,1].set(xlabel='Time (s)',ylabel='Residual (Hz)');axes[0,1].legend(fontsize=7)
        axes[1,0].axis('off');lines=[f'Available-before-scan TLE age: {age:.2f} hours',f'Inside original 48h cutoff: {r["eligible_original_48h"]}']
        for f in fits:
            if f['arm']=='fitted_c' and f['model']=='phase_small_rate':lines.append(f'±{f["phase_limit_s"]:g}s: phase={f["phase_s"]:+.2f}s; rate={f["rate_hz_s"]:+.2f}Hz/s; RMS={f["rms_hz"]:.1f}Hz')
        lines+=['No true-site coordinates used.','No production acceptance or location update.','Candidate selected during earlier diagnostic search.']
        axes[1,0].text(0,.95,'\n'.join(lines),va='top',fontsize=10,linespacing=1.8)
        ff=[f for f in fits if f['arm']=='fitted_c' and f['phase_limit_s']==120]
        axes[1,1].bar(range(4),[f['rms_hz'] for f in ff],color='#176bbb');axes[1,1].set_xticks(range(4),['Phase + offset','+ small rate','+ wider rate','Affine control'],rotation=20,ha='right');axes[1,1].set(ylabel='RMS (Hz)',title='Wide-phase diagnostic nuisance comparison')
        fig.suptitle(f'{case} · NORAD {norad} · older causal TLE / phase-bound diagnosis');fig.savefig(out/'figures'/(case+'-causal-followup.png'),dpi=150);plt.close(fig)
    write(out/'causal_followups.json',results)
    for r in results:print(r['case'],r['norad'],round(r['age_hours'],2),[(f['phase_limit_s'],round(f['phase_s'],2),round(f['rms_hz'],1),round(f['rate_hz_s'],2)) for f in r['fits'] if f['arm']=='fitted_c' and f['model']=='phase_small_rate'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);main(p.parse_args().output)
