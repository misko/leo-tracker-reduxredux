"""Local position profile for the five-track regularized orbital diagnostic."""
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT.parent/'2026_10_02_multiscan_localization'),
              str(ROOT.parent/'2026_10_02_localization_benchmark')]


def run():
    from prior_orbit_fit import modified_satellite
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets,ElementSetCatalogue
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from joint_inputs import _coordinates,_ecef,LIGHT_SPEED_KM_S
    from position_profile_grid import geodesic_position
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from scipy.optimize import least_squares
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source=ROOT/'later-tle-timing-aligned-v2/receipt.json'
    fitted_source=ROOT/'prior-orbit-fit-v2/receipt.json'
    receipt=json.loads(source.read_text());fitted=json.loads(fitted_source.read_text())
    tle=Path(receipt['latest_snapshot']['path'])
    hashes={**fitted['source_hashes'],**snapshot_files([__file__,source,fitted_source,tle])}
    assert_snapshot_unchanged(hashes)
    catalogue=parse_element_sets(tle.read_text());lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    tracks=sorted([t for t in receipt['tracks'] if np.ptp(t['time_s'])>=70],key=lambda t:-np.ptp(t['time_s']))
    grid=np.array([-500.,-100.,-50.,0.,50.,100.,500.])
    results=[];loaded={}
    for track in tracks:
        session=track['session'];number=track['catalog_number']
        if session not in loaded:loaded[session]=load_expanded_scan(session)
        data=loaded[session];scan=next(s for s in receipt['scans'] if s['session']==session)
        parameters=np.asarray(scan['later_fit']['parameters']);latitude,longitude=_coordinates(parameters[:2])
        site0=_ecef(latitude,longitude)
        pose_path=Path('/srv/bulk/leo/capture-pose/gauss-r20-lt3d-004b-20261001-v1')/(session+'.json')
        pose=json.loads(pose_path.read_text())['pose_authority']
        rooflat,rooflon=pose['latitude_deg'],pose['longitude_deg']
        hashes.update(snapshot_files([pose_path]))
        tau=parameters[6+int(np.flatnonzero(data.numbers==number)[0])]
        times=np.asarray(track['time_s']);res=np.asarray(track['later_residual_hz'])
        base=catalogue.satellites[lookup[number]];origin=scan['origin_utc_ns']
        anchor=2440587.5+(origin/1e9+float(np.mean(times))+tau)/86400
        cache={}
        def states(z):
            key=tuple(z)
            if key not in cache:
                sat=modified_satellite(base,z[1]*.001,anchor)
                cat=ElementSetCatalogue((str(number),),(number,),(sat,))
                p,v,valid=propagate_candidate_states(cat,[0],origin,times,np.array([tau+z[0]*.05]))
                assert list(valid)==[0]
                cache[key]=(p[0,0],v[0,0])
            return cache[key]
        def doppler(z,site):
            p,v=states(z);d=p-site;u=d/np.linalg.norm(d,axis=1)[:,None]
            assert np.all(u@(site/np.linalg.norm(site))>0)
            return -11.085e9*np.sum(u*v,axis=1)/LIGHT_SPEED_KM_S
        baseline=doppler(np.zeros(2),site0)
        priortrack=next(t for t in fitted['results'] if t['satellite']==number and t['scan']==track['scan'])
        main=next(m for m in priortrack['models'] if m['model']=='orbit' and m['mean_motion_prior_rev_day']==.001)
        z0=np.array(main['prior_z']);cells=[]
        for north in grid:
            for east in grid:
                radius=np.hypot(east,north)
                coords=geodesic_position(rooflat,rooflon,np.degrees(np.arctan2(east,north)),radius)
                site=_ecef(*_coordinates(coords))
                def objective(z):return np.r_[(res+baseline-doppler(z,site))/50.,z]
                def jac(z):
                    step=.001;eye=np.eye(2)*step
                    return np.column_stack([(objective(z+e)-objective(z-e))/(2*step) for e in eye])
                opt=least_squares(objective,z0,jac=jac,bounds=(-5,5),max_nfev=80,
                                  ftol=1e-9,xtol=1e-9,gtol=1e-6)
                assert opt.success
                fixed=objective(z0)
                cells.append(dict(east_m=float(east),north_m=float(north),score=float(.5*np.sum(opt.fun**2)),
                    frozen_score=float(.5*np.sum(fixed**2)),prior_z=opt.x.tolist(),
                    optimality=float(opt.optimality),bound_hit=bool(np.any(abs(opt.x)>4.99))))
        # Sky path at the known site; no invented beam exclusions.
        p,v=states(np.zeros(2));direction=p-site0;direction/=np.linalg.norm(direction,axis=1)[:,None]
        lat,lon=np.deg2rad([latitude,longitude])
        e=np.array([-np.sin(lon),np.cos(lon),0.])
        n=np.array([-np.sin(lat)*np.cos(lon),-np.sin(lat)*np.sin(lon),np.cos(lat)])
        u=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
        az=np.mod(np.degrees(np.arctan2(direction@e,direction@n)),360)
        el=np.degrees(np.arcsin(direction@u))
        origin_cell=next(c for c in cells if c['east_m']==c['north_m']==0)
        expected=.5*(len(res)*(main['stats']['rms_hz']/50)**2+np.sum(z0*z0))
        reference_score=float(.5*np.sum(np.r_[(res+baseline-doppler(z0,site0))/50.,z0]**2))
        assert abs(reference_score-expected)<.01
        out=dict(scan=track['scan'],satellite=number,receiver=track['receiver'],cells=cells,
                 old_reference_lat_lon=[latitude,longitude],roof_lat_lon=[rooflat,rooflon],old_reference_score=reference_score,
                 azimuth_start_end_deg=[float(az[0]),float(az[-1])],azimuth_range_deg=[float(az.min()),float(az.max())],
                 elevation_range_deg=[float(el.min()),float(el.max())])
        results.append(out)
        print(json.dumps({k:v for k,v in out.items() if k!='cells'}),flush=True)
    aggregated={}
    for label in ('A','B','combined'):
        selected=[r for r in results if label=='combined' or r['scan']==label]
        cells=[]
        for j in range(len(grid)**2):
            cells.append(dict(east_m=selected[0]['cells'][j]['east_m'],north_m=selected[0]['cells'][j]['north_m'],
                 score=sum(r['cells'][j]['score'] for r in selected),
                 frozen_score=sum(r['cells'][j]['frozen_score'] for r in selected)))
        origin=next(c for c in cells if c['east_m']==c['north_m']==0)
        for c in cells:
            c['delta_score']=c['score']-origin['score'];c['delta_frozen_score']=c['frozen_score']-origin['frozen_score']
        aggregated[label]=dict(origin=origin,best=min(cells,key=lambda c:c['score']),cells=cells)
    output=ROOT/'roof-position-audit';output.mkdir(exist_ok=False)
    fig,axes=plt.subplots(2,3,figsize=(14,8))
    for col,label in enumerate(aggregated):
        for row,key in enumerate(('delta_frozen_score','delta_score')):
            values=np.array([c[key] for c in aggregated[label]['cells']]).reshape(len(grid),len(grid))
            ax=axes[row,col];limit=np.max(abs(values))
            im=ax.pcolormesh(grid,grid,values,shading='nearest',cmap='RdBu_r',vmin=-limit,vmax=limit)
            ax.plot(0,0,'k+',ms=13,mew=2);ax.set_title(f"{label} · {'frozen corrections' if row==0 else 'refitted corrections'}")
            ax.set_xlabel('East offset (m)');ax.set_ylabel('North offset (m)');fig.colorbar(im,ax=ax,label='Score minus known-site score')
    fig.suptitle('Known site (+) vs nearby sites · five longest tracks · lower score is better')
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(output/'score-map.png',dpi=160)
    assert_snapshot_unchanged(hashes)
    (output/'receipt.json').write_text(json.dumps(dict(results=results,aggregated=aggregated,source_hashes=hashes,
       scope='Five longest frozen tracks, latest TLEs. Score = 0.5 sum((normalized residual/50Hz)^2) '
       '+ 0.5 sum((extra timing/.05s)^2+(mean motion change/.001rev/day)^2). '
       'RX/RF calibration stays fixed; bottom map profiles orbital/timing corrections only, not all nuisance. '
       'Zero-centered priors identical at all sites; no prior on location. '
       'Local sampled diagnostic, not exhaustive localization, marginal evidence, or full finite-set likelihood. '
       'No beam model or pointing rejection imposed.'),indent=2,allow_nan=False))


if __name__=='__main__':run()
