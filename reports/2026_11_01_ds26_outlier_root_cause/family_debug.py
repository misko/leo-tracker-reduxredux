"""Transfer suspect-family orbit hypotheses across tracks and receiver calibration."""
import argparse
import numpy as np
from sgp4.api import Satrec
from diagnose import ROOT,INPUT,ARMS,read,write,reconstruct,build
from track_debug import residual_stats
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon

SUSPECT={'DS26-0203':67935,'DS26-0070':62320,'DS26-0251':56548,'DS26-0034':53852}

def marginal_curves(raw,t,q,group,train,rate_sigma=.5):
    """Shared reference-frequency rate, per-source Gaussian constant; fixed noise."""
    groups=np.unique(group);lift=raw.copy();aliases=np.zeros((len(raw),len(groups)),int)
    for k,g in enumerate(groups):
        use=group==g;aliases[:,k]=np.rint(-raw[:,use].mean(axis=1)/PERIOD).astype(int)
        lift[:,use]+=aliases[:,k,None]*PERIOD
    X=np.column_stack([(group==g)*300. for g in groups]+[q*(t-150)*rate_sigma])
    U=X[train]/150.;G=np.eye(X.shape[1])+U.T@U;inv=np.linalg.inv(G);coef=(lift[:,train]/150.)@U@inv
    residual=lift-coef@X.T
    score=np.sum((residual[:,train]/150.)**2,axis=1)+np.sum(coef**2,axis=1)+np.linalg.slogdet(G)[1]
    return score,residual,coef,aliases

def run(case):
    z=read(INPUT/(case+'.json'));d=reconstruct(z);out=ROOT/case;n=SUSPECT[case];original=d['problems']['fitted_c'][0]
    target=next(t for t in read(out/'targets.json') if t['meta']['assigned_norad']==n)
    nums=sorted({n}|{r['norad'] for r in target['results'] if r['model']=='L3_phase'})
    tracks=[]
    for row,i,sl in zip(original.rows,original.members,original.slices):
        use=original.keep[sl]
        if row['candidate_norad']==n and use.any():tracks.append((i,use))
    times=np.concatenate([d['scan'].tracks[i]['times'][u] for i,u in tracks]);group=np.concatenate([np.full(u.sum(),k) for k,(i,u) in enumerate(tracks)])
    q=np.concatenate([np.full(u.sum(),d['scan'].tracks[i]['rf_hz']/11.5e9) for i,u in tracks]);ledger=read(out/'tle-ledger.json')
    # Whole-track partition is fixed in advance; this is conditional transfer of a
    # shortlist nominated using one original track, not independent catalogue discovery.
    rng=np.random.default_rng(20261101);order=rng.permutation(len(tracks));train_groups=order[:max(1,len(tracks)//2)]
    masks={'all':np.ones(len(times),bool),'whole_track_train':np.isin(group,train_groups)}
    levels={'small_rate':.5,'rate_discrepancy':2.};pp=np.linspace(-30,30,301);results=[]
    native_metadata=[dict(index=k,key=d['scan'].tracks[i]['key'],receiver=d['scan'].tracks[i]['receiver'],channel=d['scan'].tracks[i]['channel'],
        times_s=d['scan'].tracks[i]['times'][u],observation_ids=[o for o,b in zip(d['scan'].tracks[i]['observation_ids'],u) if b],
        graph_pieces=len(d['scan'].tracks[i]['pieces'])) for k,(i,u) in enumerate(tracks)]
    for regime in ('causal','later'):
        available=[v for v in nums if str(v) in ledger[regime]];grid=np.arange(-40.,341.)
        cat=ElementSetCatalogue(tuple(map(str,available)),tuple(available),tuple(Satrec.twoline2rv(*ledger[regime][str(v)]['lines']) for v in available))
        pos,vel,good=ecef_states(cat,z['scan_receipt']['origin_utc_ns'],grid)
        for arm in ARMS:
            old,x=d['problems'][arm];saved=read(out/(f'extended_omit_{n}.json' if (out/f'extended_omit_{n}.json').exists() else f'omit_{n}.json'))[arm]
            cavity,dd=build(d,z,arm,np.asarray(saved['reference']),omit=n)
            for calibration,p,point in [('published',old,x),('family_omitted',cavity,np.asarray(saved['x']))]:
                state=p.state(point);values=np.concatenate([(d['scan'].tracks[i]['values']-p.scan.hardware(d['scan'].tracks[i],state['beta'])-
                    d['scan'].tracks[i]['rf_hz']/11.5e9*d['scan'].rx_basis[i]@state['smooth'][d['scan'].tracks[i]['receiver']-1])[u] for i,u in tracks])
                for k,sat in enumerate(available):
                    if not good[k]:continue
                    bb=dict(time_s=grid,position_km=np.broadcast_to(pos[k],(len(pp),*pos[k].shape)),velocity_km_s=np.broadcast_to(vel[k],(len(pp),*vel[k].shape)))
                    f,e=paired_phase_frequency(bb,np.tile(times,len(pp)),np.repeat(np.arange(len(pp)),len(times)),pp,*latlon(point));f=f.reshape(len(pp),-1)*q;e=e.reshape(len(pp),-1)
                    for level,rate in levels.items():
                        for split,mask in masks.items():
                            cost,res,coef,aliases=marginal_curves(values-f,times,q,group,mask,rate)
                            cost=np.where(e[:,mask].min(axis=1)>=0,cost+(pp/5)**2,np.inf)
                            if not np.isfinite(cost).any():continue
                            j=int(np.argmin(cost));per=[]
                            for g in range(len(tracks)):
                                use=group==g;r=res[j,use];u=times[use]-times[use].mean();offset=r.mean();slope=u@r/(u@u)
                                per.append(dict(index=g,training=bool(mask[use].all()),**residual_stats(times[use],r),
                                    free_constant_rms_hz=float(np.sqrt(np.mean((r-offset)**2))),
                                    free_affine_rms_hz=float(np.sqrt(np.mean((r-offset-slope*u)**2)))))
                            results.append(dict(arm=arm,regime=regime,calibration=calibration,norad=sat,level=level,split=split,score=float(cost[j]),
                                phase_s=float(pp[j]),rate_hz_s=float(coef[j,-1]*rate),offsets_hz=coef[j,:-1]*300,aliases=aliases[j],
                                residual_hz=res[j],prediction_orbit_hz=f[j],corrected_observation_hz=values,
                                times_s=times,group=group,per_track=per,position=point,
                                all_tracks_noise_pass=all(r['noise']['noise_screen_pass'] for r in per)))
                print(case,regime,arm,calibration,'family done',flush=True)
    write(out/'family_diagnostic.json',dict(case=case,suspect=n,tracks=native_metadata,results=results,train_groups=train_groups,
        scope='Same suspect-family native points; shared phase and reference-frequency rate; per-track offset priors 300Hz; noise150Hz; phase prior5s; all curves weight equally per native point. Frozen published or omission-fit receiver calibration. No inference truth.',
        caveat='Shortlist originated from one inspected full track. Whole-track transfer is conditional on that selection and is not independent identity validation; offset/affine held-track minima are shape diagnostics, not prediction likelihoods.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');run(p.parse_args().case)
