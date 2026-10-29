"""Inspect whole-curve versus 20-second orbit fits and simultaneous residuals."""
import argparse
import copy
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context,exact,PHASES,ARMS
from leo.analysis.research.track_recovery_diagnostics import shortlist,profile_rate
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon


def run(args):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from investigate_ds23_0268_remaining_tracks import family_frequency,corrected_observation
    inv=read(args.inventory);diag=read(args.diagnostics);d=context(inv);scan=d['scan']
    record=next(r for r in diag['tracks'] if r['track_id']==args.track) if args.track else max(diag['tracks'],key=lambda r:r['remaining_points'])
    track=scan.tracks[record['track_index']];t=track['times'];out=args.output;out.mkdir(parents=True,exist_ok=False)
    full={a:min((r for r in record['trials'][a]['constant'] if r['search']=='current'),key=lambda r:r['cost']) for a in ARMS}
    candidate=full['c0']['candidate_index'];observed={};neighbors=[]
    for arm,(p,x) in d['problems'].items():
        observed[arm]=corrected_observation(p,x,record['track_index'])
    p,x=d['problems']['c0'];segments=[]
    for start in np.arange(min(t),max(t),20.):
        mask=(t>=start)&(t<start+20)
        if mask.sum()<8:continue
        sub=copy.copy(track);sub['times']=t[mask];sub['values']=track['values'][mask]
        ff=[];ee=[]
        for phase in PHASES:
            f,e=phase_frequency_grid(scan.sky,sub['times'],*latlon(x),phase_seconds=phase);ff.append(f);ee.append(e)
        guesses=shortlist(observed['c0'][mask],sub['times'],track['rf_hz']/11.5e9,np.array(ff),np.array(ee),sub['times'],PHASES,top=3)
        guesses+=[dict(candidate_index=candidate,phase_s=full['c0']['phase_s'])]
        trials={}
        for arm,(pa,xa) in d['problems'].items():
            trials[arm]=[exact(scan,sub,observed[arm][mask],g,xa,'constant') for g in guesses]
        segments.append(dict(start_s=float(start),points=int(mask.sum()),trials=trials))
    # Retained curves are selected by temporal overlap, not residual agreement.
    p,x=d['problems']['fitted_c']
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        if not p.keep[sl].any() or i==record['track_index']:continue
        other=scan.tracks[i];mask=(other['times']>=min(t))&(other['times']<=max(t))&p.keep[sl]
        if mask.sum()<8:continue
        f,_=family_frequency(p,x,row['candidate_index'],times=other['times'])
        y=corrected_observation(p,x,i);r=profile_rate(y,other['rf_hz']/11.5e9*f,other['times'])
        neighbors.append(dict(component=other['key'],receiver=other['receiver'],channel=other['channel'],norad=row['candidate_norad'],
            times_s=other['times'][mask],residual_hz=r['residual_hz'][0][mask],overlap_points=int(mask.sum())))
    result=dict(job=inv['job'],track=record['component'],track_id=record['track_id'],full=full,segments=segments,neighbors=neighbors,
                no_new_associations=True,segment_fits_have_independent_phase_and_offset=True,
                segments_are_diagnostics_not_evidence_for_splitting=True)
    write(out/'result.json',result)
    fig,axs=plt.subplots(3,1,figsize=(13,11),layout='constrained')
    f=full['fitted_c'];times=np.array(f['times_s']);y=np.array(f['corrected_observation_hz']);r=np.array(f['residual_hz'])
    axs[0].scatter(times,y/1000,s=15,color='#cc1748',label='Receiver-corrected full graph track')
    axs[0].plot(times,(y-r)/1000,color='#0072b2',label=f"Causal orbit + fitted alias/offset, NORAD {f['norad']}")
    axs[0].set_ylabel('Corrected CFO (kHz)');axs[0].legend()
    for arm,q in full.items():axs[1].plot(q['times_s'],q['residual_hz'],'.-',ms=3,label=f"Whole {arm}: {q['rms_hz']:.1f} Hz RMS")
    for s in segments:
        choices=s['trials']['fitted_c'];same=min((q for q in choices if q['candidate_index']==candidate),key=lambda q:q['cost'])
        axs[1].plot(same['times_s'],same['residual_hz'],color='#009e73',alpha=.65)
        axs[1].axvline(s['start_s'],color='gray',alpha=.2)
    axs[1].plot([],[],color='#009e73',label='Same satellite: independent phase/offset per 20s')
    axs[1].set_ylabel('Residual (Hz)');axs[1].legend(fontsize=8)
    selected=sorted(neighbors,key=lambda q:(q['norad']!=f['norad'],q['receiver']!=track['receiver'],-q['overlap_points']))[:10]
    for q in selected:axs[2].plot(q['times_s'],q['residual_hz'],'.-',ms=3,label=f"{q['norad']} RX{q['receiver']} CH{q['channel']}")
    axs[2].set_ylabel('Retained-curve residual (Hz)');axs[2].set_title('Simultaneous retained evidence, after its existing orbital correction')
    if selected:axs[2].legend(ncol=3,fontsize=7)
    for ax in axs:
        ax.grid(alpha=.2);ax.set_xlabel('Scan time (s)')
    for ax in axs[1:]:ax.axhline(0,color='gray',lw=.7)
    fig.suptitle(inv['job']['label']+' '+record['component'].split('-RF')[0]+'\nWhole versus segment orbit fits; diagnostic only')
    fig.savefig(out/'diagnostic.png',dpi=140);plt.close(fig)
    print(inv['job']['label'],record['component'],[(s['start_s'],min(s['trials']['fitted_c'],key=lambda q:q['cost'])['norad']) for s in segments],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('inventory','diagnostics','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--track');run(p.parse_args())
