"""Bounded independent-scan replication of frozen curvature screening."""
import copy
import csv
import json
import time
import numpy as np
from curvature_position_profile import ROOT, curvature
from prepare_four_scan_comparison import OUTPUT
from curvature_threshold_sweep import screen
from find_profile_minimum import local_offset

THRESHOLDS=(None,1.1,1.075,1.05,1.025)


def fitted_residual(data, objective, fit):
    from finite_set_likelihood import circular_residual
    prediction,_=objective.base.predict(np.asarray(fit['vector'])[:objective.size])
    prediction=prediction+(objective.features@np.asarray(fit['rf_coefficient_hz_per_ghz']))[:,None]
    return circular_residual(data.measured[:,None],prediction,objective.likelihood.alias_hz)*11.085e9/data.rf[:,None]


def run(scan_index=None):
    import prepare_scans as prep
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from position_profile_grid import run_profile, geodesic_position
    from joint_inputs import _coordinates
    from rf_calibration_diagnostic import CalibrationObjective
    from finite_set_fit import snapshot_files, assert_snapshot_unchanged
    from staged_fit import fit_receiver_lines
    from orbit_backfill_prototype import build_initial_inventory, serializable
    from group_summed_viterbi_backfill import recover_group_track, _collision_summary
    from scipy.optimize import minimize
    started=time.monotonic(); prep.ROOT=OUTPUT
    selection=json.loads((OUTPUT/'selection.json').read_text())
    assert_snapshot_unchanged(selection['source_hashes'])
    latest=ROOT/'later-tle-timing-aligned-v2/receipt.json'
    tle=json.loads(latest.read_text())['latest_snapshot']['path']
    catalogue=parse_element_sets(__import__('pathlib').Path(tle).read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    hashes=snapshot_files([__file__,latest,tle,OUTPUT/'selection.json',OUTPUT/'preparation.json'])
    out=OUTPUT/'comparison-v2';out.mkdir(exist_ok=True)
    def save(path,value):
        path.write_text(json.dumps(serializable(value),indent=2,allow_nan=False)+'\n')
    results=[]
    for index,pose in enumerate(selection['poses']):
        if scan_index is not None and index+1!=scan_index:continue
        sid=pose['session'];directory=out/sid;directory.mkdir(exist_ok=True)
        if (directory/'result.json').exists():
            results.append(json.loads((directory/'result.json').read_text()));continue
        source,data=prep.load_scan(sid);bundle_dir=OUTPUT/'scans'/sid
        seed=json.loads((bundle_dir/'seed.json').read_text());manifest=json.loads((bundle_dir/'bundle.json').read_text())
        hashes.update(snapshot_files([bundle_dir/n for n in ('seed.json','bundle.json','bundle.npz')]))
        sats=np.asarray(seed['satellites'],int);numbers=data.numbers[sats];probability=.8/len(sats)
        lat,lon=pose['latitude'],pose['longitude'];center=geodesic_position(lat,lon,0,0)
        jac=np.column_stack([(geodesic_position(lat,lon,b,1)-geodesic_position(lat,lon,b+180,1))/2 for b in (90,0)])*100
        indices=[lookup[int(n)] for n in numbers]
        p,v,valid=propagate_candidate_states(catalogue,indices,manifest['origin_utc_ns'],data.nodes,np.array([0.]))
        if list(valid)!=indices:raise ValueError('missing propagated candidate')
        data.position=data.position.copy();data.velocity=data.velocity.copy()
        data.position[sats]=p[:,0];data.velocity[sats]=v[:,0]
        # Initial RX lines use the new ephemeris at the verified site. This only
        # seeds optimization: no per-track linear/quadratic corrections enter it.
        raw=copy.copy(source);raw.position=data.position;raw.velocity=data.velocity
        rough=copy.deepcopy(seed['rough']);rough['position_km']=center
        evaluations=[]
        def fitted(chosen,position,start):
            vector=None
            for _ in range(8):
                f=run_profile(data,start['parameters'],chosen,start['rf_coefficient_hz_per_ghz'],position,
                    probability_override=probability,start_vector=vector,budget_s=8)
                vector=f['vector']
                if f['success']:break
            save(directory/f'fit-{len(evaluations):04d}.json',f)
            evaluations.append(dict(position=position,candidates=data.numbers[chosen],objective=f['objective'],success=f['success']))
            if not f['success']:raise RuntimeError(f'{sid}: unconverged profile {f["status"]}')
            return f
        print('BASELINE',sid,flush=True)
        initial_trials=[]
        for shift in (0.,float(seed['initial'][6+sats[0]])):
            if any(t['shift']==shift for t in initial_trials):continue
            params=fit_receiver_lines(prep.ShiftedData(raw,shift),rough);params[6:]=shift
            f=fitted(sats,center,dict(parameters=params,rf_coefficient_hz_per_ghz=[0.]))
            initial_trials.append(dict(shift=shift,fit=f))
        roof=min(initial_trials,key=lambda t:t['fit']['objective'])['fit'];save(directory/'unfiltered-roof.json',roof)
        obj=CalibrationObjective(data,np.asarray(roof['parameters']),sats,False,8)
        obj.base.deadline=float('inf');obj.likelihood.detection_probability=probability
        obj.evaluate(np.asarray(roof['vector']))
        # Use the identical family-row geometry and ephemeris used by the loss.
        # FamilyGeometryData.predict delegates to raw source rows, so it must
        # NOT be used to reconstruct these residuals.
        residual=fitted_residual(data,obj,roof)
        arrays=dict(catalog_numbers=numbers,times_s=data.times,group=data.group,receiver=data.receiver,
                    channel=data.channel,posterior=obj.likelihood.last_result['row_association_probability'],residual_hz=residual)
        owners,proposals=build_initial_inventory(seed,source.group,source.times,source.channel,numbers)
        recovered=[];tracks=[]
        for (number,rx),initial in sorted(proposals.items()):
            column=int(np.flatnonzero(numbers==number)[0]);track=recover_group_track(arrays,column,rx,initial,owners)
            recovered.append(track);rows=track['viterbi_rows']
            tracks.append(dict(catalog_number=number,receiver=rx,rows=rows,count=len(rows),
                span_s=float(np.ptp(data.times[rows])) if len(rows) else 0.,recovery_status=track['status'],
                **curvature(data.times[rows],residual[rows,column])))
        collisions=_collision_summary(recovered,'viterbi_rows')
        if collisions['colliding_row_count']:raise ValueError('track collisions')
        for track in recovered:
            for proposal in track['initial_proposals']:
                proposal['groups']=sorted(proposal['groups'])
        save(directory/'tracks.json',dict(tracks=tracks,recovery=recovered,collisions=collisions))
        cache={};variants=[];previous=center.copy()
        for threshold in THRESHOLDS:
            policy=screen(numbers,tracks,threshold);key=tuple(policy['kept'])
            print('SCREEN',sid,threshold,policy,flush=True)
            if not key:
                variants.append(dict(threshold=threshold,policy=policy,status='no candidates'));continue
            if key in cache:
                variants.append(dict(cache[key],threshold=threshold));continue
            chosen=np.asarray([s for s in sats if data.numbers[s] in key]);bank=[]
            base=roof if threshold is None else fitted(chosen,center,roof);bank.append(base)
            def profile(position):
                nearest=min(bank,key=lambda f:np.linalg.norm(np.asarray(f['parameters'][:2])-position))
                if np.linalg.norm(np.asarray(nearest['parameters'][:2])-position)<1e-9:return nearest
                # Continuation avoids jumping into the unsupported clutter basin.
                distance=np.linalg.norm(np.asarray(nearest['parameters'][:2])-position)
                startpos=np.asarray(nearest['parameters'][:2]);start=nearest
                for fraction in np.linspace(0,1,int(np.ceil(distance/.5))+1)[1:]:
                    start=fitted(chosen,startpos+fraction*(position-startpos),start);bank.append(start)
                return start
            def fun(position):
                f=profile(position)
                return (f['objective']-base['objective'])/50.,np.asarray(f['free_position_gradient'])/50.
            cardinal=[profile(geodesic_position(lat,lon,b,50))['objective'] for b in (90,270,0,180)]
            gradient=np.asarray(base['free_position_gradient'])@jac
            fd=np.array([cardinal[0]-cardinal[1],cardinal[2]-cardinal[3]])
            attempts=[]
            second=previous if np.linalg.norm(previous-center)>.1 else center+np.array([.4,-.6])
            for start in (center,second):
                opt=minimize(fun,start,jac=True,method='L-BFGS-B',bounds=[(c-5,c+5) for c in center],
                    options=dict(ftol=1e-12,gtol=2e-5,maxiter=35,maxls=12))
                f=profile(opt.x);en=local_offset(lat,lon,*_coordinates(opt.x))
                attempts.append(dict(position_km=opt.x,east_m=en[0],north_m=en[1],distance_m=float(np.linalg.norm(en)),
                    objective=f['objective'],delta_score=f['objective']-base['objective'],success=bool(opt.success),
                    message=str(opt.message),gradient=f['free_position_gradient']))
            best=min(attempts,key=lambda a:a['objective']);previous=np.asarray(best['position_km']);h=.05
            neighbor=[]
            for dx,dy in ((h,0),(-h,0),(0,h),(0,-h),(h,h),(h,-h),(-h,h),(-h,-h)):
                neighbor.append(profile(previous+[dx,dy])['objective']-best['objective'])
            cross=(neighbor[4]-neighbor[5]-neighbor[6]+neighbor[7])/(4*h*h)
            H=np.array([[(neighbor[0]+neighbor[1])/h**2,cross],[cross,(neighbor[2]+neighbor[3])/h**2]])
            row=dict(threshold=threshold,policy=policy,status='evaluated',roof_gradient_per_100m=gradient,
                roof_finite_difference_per_100m=fd,gradient_check_passed=bool(np.allclose(fd,gradient,rtol=.02,atol=.005)),
                roof_support=float(sum(base['satellite_support'])),best=best,attempts=attempts,
                hessian_eigenvalues=np.linalg.eigvalsh(H),minimum_neighbor_increase=min(neighbor),
                start_agreement_m=float(np.linalg.norm(np.asarray(attempts[0]['position_km'])-attempts[1]['position_km'])*1000),
                boundary=bool(np.any(np.abs(previous-center)>4.99)))
            variants.append(row);cache[key]=row;save(directory/'partial.json',variants)
            print('RESULT',sid,threshold,best['distance_m'],gradient,flush=True)
        result=dict(session=sid,scan_index=index+1,origin_utc_ns=manifest['origin_utc_ns'],tracks=tracks,
                    candidates=numbers,variants=variants,initial_trials=initial_trials,evaluations=evaluations)
        save(directory/'result.json',result);results.append(result)
    assert_snapshot_unchanged(hashes)
    if scan_index is not None:
        save(out/f'worker-{scan_index}.json',dict(source_hashes=hashes,elapsed_s=time.monotonic()-started))
        return
    for index in range(1,5):
        worker=out/f'worker-{index}.json'
        if worker.exists():
            record=json.loads(worker.read_text());assert_snapshot_unchanged(record['source_hashes'])
            hashes.update(record['source_hashes'])
    receipt=dict(scans=results,source_hashes=hashes,elapsed_s=time.monotonic()-started,
        scope='Four chronologically preselected existing DS13 scans. Same finite-set score, priors, later archived TLE snapshot, '
        'RX/RF/timing nuisance refits, curvature diagnostic and strict thresholds as A/B. Independent seed candidate banks '
        'from archived top-five reviews; NOT a replay of A/B all-visible expansion and compact pruning. '
        'Seed-anchored group-summed Viterbi memberships are frozen at the verified roof before screening. '
        'Unassessed candidates retained explicitly. Fixed original per-candidate detection probability; all groups retained. '
        'Two-start local search with +/-5 regional-km safety bounds, not global minima or validated identity evidence. '
        'Compare score changes within each subset only. No new RF collection or production writes.')
    save(out/'receipt.json',receipt);plot(out,receipt)


def plot(out,receipt):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(16,5));rows=[]
    labels=['Off','1.1','1.075','1.05','1.025']
    for scan in receipt['scans']:
        valid=[v for v in scan['variants'] if v['status']=='evaluated'];x=[THRESHOLDS.index(v['threshold']) for v in valid]
        label=f"{scan['scan_index']}: {scan['session'].removeprefix('scan-fw-')[:8]}"
        axes[0].plot(x,[v['best']['distance_m']/1000 for v in valid],'o-',label=label)
        axes[1].plot(x,[np.linalg.norm(v['roof_gradient_per_100m']) for v in valid],'o-')
        axes[2].plot(x,[len(v['policy']['kept']) for v in valid],'o-')
        for v in valid:
            rows.append(dict(scan=scan['scan_index'],session=scan['session'],threshold='off' if v['threshold'] is None else v['threshold'],
                retained=len(v['policy']['kept']),unassessed=len(v['policy']['unassessed']),distance_m=v['best']['distance_m'],
                east_m=v['best']['east_m'],north_m=v['best']['north_m'],delta_score=v['best']['delta_score'],
                roof_gradient_norm=float(np.linalg.norm(v['roof_gradient_per_100m'])),support=v['roof_support'],
                start_agreement_m=v['start_agreement_m'],boundary=v['boundary'],gradient_check=v['gradient_check_passed']))
    for ax,title in zip(axes,('Local minimum distance from roof (km)','Roof score gradient magnitude / 100 m','Retained satellite candidates')):
        ax.set_title(title);ax.set_xticks(range(5),labels);ax.set_xlabel('Exclude if linear RMS / quadratic RMS > cutoff');ax.grid(alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('Four additional DS13 scans · frozen curvature-filter sensitivity',fontsize=16)
    fig.text(.5,.01,'Same score and priors; new seed banks (no all-visible expansion). Unassessed candidates retained. Local, in-sample diagnostic.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.055,1,.94));fig.savefig(out/'comparison.png',dpi=170);plt.close(fig)
    with (out/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=range(1,5))
    run(parser.parse_args().scan)
