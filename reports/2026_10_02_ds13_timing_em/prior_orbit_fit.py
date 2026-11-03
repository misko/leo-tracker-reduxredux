"""Frozen-track MAP diagnostic with SGP4 mean-motion and timing perturbations."""
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT.parent/'2026_10_02_multiscan_localization'),
              str(ROOT.parent/'2026_10_02_localization_benchmark')]


def modified_satellite(base,dn_rev_day,anchor_jd):
    from sgp4.api import Satrec,WGS72
    dn=dn_rev_day*2*np.pi/1440
    elapsed=(anchor_jd-base.jdsatepoch-base.jdsatepochF)*1440
    satellite=Satrec()
    satellite.sgp4init(WGS72,base.operationmode,base.satnum,
        base.jdsatepoch-2433281.5+base.jdsatepochF,base.bstar,base.ndot,base.nddot,
        base.ecco,base.argpo,base.inclo,base.mo-dn*elapsed,base.no_kozai+dn,base.nodeo)
    return satellite


def folds(times):
    labels=np.minimum(((times-times.min())/np.ptp(times)*5).astype(int),4)
    for k in range(5):
        test=labels==k
        train=(times<times[test].min()-1)|(times>times[test].max()+1)
        yield train,test


def run():
    from leo.sky.propagation import parse_element_sets,ElementSetCatalogue
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from all_visible_bank import load_expanded_scan
    from joint_inputs import _coordinates,_ecef,LIGHT_SPEED_KM_S
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from residual_trend_audit import stats
    from scipy.optimize import least_squares
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source=ROOT/'later-tle-timing-aligned-v2/receipt.json'
    receipt=json.loads(source.read_text());tle=Path(receipt['latest_snapshot']['path'])
    hashes={**receipt['source_hashes'],**snapshot_files([__file__,source,tle])}
    assert_snapshot_unchanged(hashes)
    catalogue=parse_element_sets(tle.read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    tracks=sorted([t for t in receipt['tracks'] if np.ptp(t['time_s'])>=70],key=lambda t:-np.ptp(t['time_s']))
    results=[];loaded={};fig,axes=plt.subplots(5,1,figsize=(12,15))
    for k,track in enumerate(tracks):
        session=track['session'];number=track['catalog_number']
        if session not in loaded:loaded[session]=load_expanded_scan(session)
        data=loaded[session];scan=next(s for s in receipt['scans'] if s['session']==session)
        parameters=np.asarray(scan['later_fit']['parameters'])
        satellite=int(np.flatnonzero(data.numbers==number)[0]);tau=parameters[6+satellite]
        times=np.array(track['time_s']);res=np.array(track['later_residual_hz'])
        site=_ecef(*_coordinates(parameters[:2]));up=site/np.linalg.norm(site)
        base=catalogue.satellites[lookup[number]];origin=scan['origin_utc_ns']
        anchor_jd=2440587.5+(origin/1e9+float(np.mean(times))+tau)/86400
        def doppler(dt,dn):
            sat=modified_satellite(base,dn,anchor_jd)
            cat=ElementSetCatalogue((str(number),),(number,),(sat,))
            pos,vel,valid=propagate_candidate_states(cat,[0],origin,times,np.array([tau+dt]))
            if list(valid)!=[0]:raise ValueError('invalid perturbed propagation')
            delta=pos[0,0]-site;direction=delta/np.linalg.norm(delta,axis=1)[:,None]
            if not np.all(direction@up>0):raise ValueError('perturbation below horizon')
            return -11.085e9*np.sum(direction*vel[0,0],axis=1)/LIGHT_SPEED_KM_S
        baseline=doppler(0,0)
        # Ensure reinitialization does not change the unperturbed SGP4 state.
        cat=ElementSetCatalogue((str(number),),(number,),(base,))
        pos,vel,valid=propagate_candidate_states(cat,[0],origin,times,np.array([tau]))
        delta=pos[0,0]-site;direction=delta/np.linalg.norm(delta,axis=1)[:,None]
        replay=-11.085e9*np.sum(direction*vel[0,0],axis=1)/LIGHT_SPEED_KM_S
        parity=float(np.max(np.abs(replay-baseline)))
        assert parity<1e-6
        def fit(model,sdn,train):
            scales=np.array([.05] if model=='timing' else [.05,100. if model=='timing_offset' else sdn])
            def residual(z):
                dt=z[0]*scales[0]
                dn=z[1]*scales[1] if model=='orbit' else 0.
                offset=z[1]*scales[1] if model=='timing_offset' else 0.
                return res+baseline-doppler(dt,dn)-offset
            def objective(z):return np.r_[residual(z)[train]/50.,z]
            def jacobian(z):
                # Absolute scaled steps avoid nanosecond quantization at z=0.
                step=.001
                eye=np.eye(len(z))*step
                return np.column_stack([(objective(z+e)-objective(z-e))/(2*step) for e in eye])
            opt=least_squares(objective,np.zeros(len(scales)),bounds=(-5,5),
                              jac=jacobian,ftol=1e-9,xtol=1e-9,gtol=1e-6,max_nfev=100)
            if not opt.success:raise RuntimeError(opt.message)
            return residual(opt.x),dict(parameters=(opt.x*scales).tolist(),prior_z=opt.x.tolist(),
                success=bool(opt.success),optimality=float(opt.optimality),bound_hit=bool(np.any(abs(opt.x)>4.99)))
        models=[]
        for model,sdn in [('timing',.001),('timing_offset',.001),('orbit',.0003),('orbit',.001),('orbit',.003)]:
            after,detail=fit(model,sdn,np.ones(len(times),bool))
            cv=np.full(len(times),np.nan);fold_details=[]
            for train,test in folds(times):
                held,fd=fit(model,sdn,train);cv[test]=held[test];fold_details.append(fd)
            entry=dict(model=model,mean_motion_prior_rev_day=sdn if model=='orbit' else None,
                **detail,stats=stats(times,after),cv_rms_hz=float(np.sqrt(np.mean(cv**2))),
                fold_fits=fold_details,residual_hz=after.tolist())
            models.append(entry)
            if model=='orbit' and sdn==.001:chosen=after
        result=dict(scan=track['scan'],satellite=number,receiver=track['receiver'],
            duration_s=float(np.ptp(times)),points=len(times),baseline=stats(times,res),
            zero_perturbation_parity_hz=parity,models=models,time_s=times.tolist())
        results.append(result)
        ax=axes[k];ax.scatter(times,res,s=12,alpha=.55,label='Latest-TLE baseline')
        ax.scatter(times,chosen,s=12,alpha=.7,label='Timing + mean motion, zero-centered priors')
        ax.axhline(0,color='gray',lw=.8);ax.grid(alpha=.2)
        main=next(m for m in models if m['model']=='orbit' and m['mean_motion_prior_rev_day']==.001)
        ax.set_title(f"{track['scan']} · {number} / RX{track['receiver']} | RMS {result['baseline']['rms_hz']:.1f} → "
                     f"{main['stats']['rms_hz']:.1f} Hz; blocked CV {main['cv_rms_hz']:.1f} Hz")
        ax.set_ylabel('Residual (Hz)')
        print(json.dumps(dict(scan=track['scan'],satellite=number,models=[{key:value for key,value in m.items()
            if key not in ('residual_hz','fold_fits')} for m in models])),flush=True)
    axes[0].legend(fontsize=9);axes[-1].set_xlabel('Receive time (s)')
    fig.suptitle('Regularized SGP4 orbital-rate diagnostic · longest five tracks')
    fig.tight_layout(rect=(0,0,1,.98));output=ROOT/'prior-orbit-fit-v2';output.mkdir(exist_ok=False)
    fig.savefig(output/'comparison.png',dpi=150)
    assert_snapshot_unchanged(hashes)
    (output/'receipt.json').write_text(json.dumps(dict(results=results,source_hashes=hashes,
        priors=dict(timing_sigma_s=.05,mean_motion_sigma_rev_day=[.0003,.001,.003],
                    offset_control_sigma_hz=100.,observation_sigma_normalized_hz=50.,hard_bounds_sigma=5),
        scope='Frozen latest-TLE final points, aliases, receiver calibration and RF term. Exact SGP4 differential '
              'Doppler changes anchored to archived residuals. Mean motion perturbed with mean anomaly compensated '
              'to preserve Keplerian phase at track midpoint; not a full orbit determination. '
              'Five contiguous held-out blocks, 1s guards; prior full-scan calibration and selection are not held out. '
              'Noise scale and priors are diagnostic assumptions, not measured orbit covariance. '
              'No operational fit or associations updated.'),indent=2,allow_nan=False))


if __name__=='__main__':run()
