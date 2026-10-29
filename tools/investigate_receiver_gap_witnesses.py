"""Exploratory native-GLRT witnesses in DS24-0070's RX1 calibration gap.

Windows follow the observed branches in the published raw-CFO plot. They are
explicit discovery selections, not independently validated recovered tracks.
No evaluation coordinate, future TLE or GPS-driven choice enters the screen.
"""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context,exact
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from leo.analysis.research.track_recovery_diagnostics import profile_rate,shortlist
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon


def run(args):
    out=args.output;out.mkdir(exist_ok=False);inv=read(args.inventory);d=context(inv);scan=d['scan'];root=Path(inv['job']['root'])/inv['job']['case']
    obs=read(root/'observations.json');definitions=[
        dict(name='CH3_early_graph',channel=3,start=46,end=61,low=0,high=500000),
        dict(name='CH3_gap_untracked',channel=3,start=61,end=76,low=0,high=500000),
        dict(name='CH4_low_branch',channel=4,start=46,end=75,low=0,high=200000),
        dict(name='CH4_high_branch',channel=4,start=54,end=62,low=200000,high=300000)]
    tracks=[]
    for spec in definitions:
        rows=sorted([o for o in obs if o['receiver']==1 and o['channel']==spec['channel'] and spec['start']<=o['time_s']<spec['end'] and spec['low']<=o['measured_cfo_hz']<spec['high']],key=lambda o:o['time_s'])
        rf={r['actual_rf_hz'] for r in rows}
        if len(rf)!=1 or len(rows)<4:raise ValueError('witness needs one RF and at least four points')
        tracks.append(dict(key=spec['name'],receiver=1,channel=spec['channel'],bank='CH1-4',rf_hz=next(iter(rf)),
            times=np.array([r['time_s'] for r in rows]),values=np.array([r['measured_cfo_hz'] for r in rows]),observation_ids=[r['observation_id'] for r in rows]))
    write(out/'protocol.json',dict(job=inv['job'],definitions=definitions,tracks=tracks,selection='Manually delineated CFO branches; discovery only',
        candidate_bank='complete original causal catalogue',phases_s=list(np.arange(-15.,15.1,3.)),position='original inferred endpoint per c arm',
        GPS_used=False,future_TLE=False,accepted_recovery=False,calibration_frozen=True,independent_validation=False))
    results=[]
    for arm,(p,x) in d['problems'].items():
        state=p.state(x);active=sorted({row['candidate_index'] for row,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()})
        active=sorted(set(active)|{e['candidate_index'] for e in d['entries']})
        knots=np.linspace(45,77,33);phases=np.arange(-15.,15.1,3.);ff=[];ee=[]
        for phase in phases:
            f,e=phase_frequency_grid(scan.sky,knots,*latlon(x),phase_seconds=phase);ff.append(f);ee.append(e)
        for track in tracks:
            q=track['rf_hz']/11.5e9;t=track['times'];y=track['values']-scan.hardware(track,state['beta'])-q*projected_receiver_basis(t)@state['smooth'][0]
            fixed=[]
            for j in active:
                f,e=family_frequency(p,x,j,times=t);terms=profile_rate(y,q*f,t,bias_sigma_hz=300.)
                if e.min()<0:continue
                fixed.append(dict(norad=int(scan.norads[j]),candidate_index=j,phase_s=float(state['phases'][j]),
                    RMS_hz=float(terms['rms_hz'][0]),offset_hz=float(terms['bias_hz'][0]),cost=float(terms['cost'][0]),
                    residual_hz=terms['residual_hz'][0],alias=int(terms['alias'][0]),minimum_elevation_deg=float(e.min()),
                    receiver_and_orbit_not_refitted=True))
            fixed.sort(key=lambda r:r['cost']);offers=shortlist(y,t,q,np.asarray(ff),np.asarray(ee),knots,phases,top=5)
            refined=sorted([exact(scan,track,y,offer,x,'constant') for offer in offers],key=lambda r:r['cost'])
            results.append(dict(arm=arm,track=track,fixed_family_top=fixed[:5],free_phase_top=refined,corrected_observation_hz=y))
            print(arm,track['key'],'fixed',[(r['norad'],round(r['RMS_hz'],1)) for r in fixed[:3]],'free',[(r['norad'],round(r['rms_hz'],1)) for r in refined[:3]],flush=True)
    write(out/'result.json',dict(job=inv['job'],rows=results,accepted_recovery=False))
    fig,axs=plt.subplots(4,2,figsize=(13,12),layout='constrained')
    for k,track in enumerate(tracks):
        row=next(r for r in results if r['arm']=='fitted_c' and r['track']['key']==track['key']);t=track['times'];axs[k,0].scatter(t,track['values']/1000,c='black',s=20)
        for color,kind in [('#4477aa','fixed_family_top'),('#cc3311','free_phase_top')]:
            best=row[kind][0];res=np.asarray(best['residual_hz']);axs[k,0].plot(t,(track['values']-res)/1000,c=color,label=f"{best['norad']} / {'shared phase' if kind=='fixed_family_top' else 'free phase'}")
            axs[k,1].plot(t,res,'.-',c=color,label=str(best['norad']))
        axs[k,0].set(title=track['key'],ylabel='Native CFO (kHz)');axs[k,0].legend(fontsize=8);axs[k,1].set(ylabel='Residual (Hz)');axs[k,1].axhline(0,c='black',lw=.8)
        for ax in axs[k]:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
    fig.suptitle('DS24-0070: short witness branches, diagnostic fits only\nShared-phase candidates use existing inferred calibration; free-phase candidates cannot establish identity')
    fig.savefig(out/'witness_candidates.png',dpi=145);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
