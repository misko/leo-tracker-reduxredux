"""Frozen-candidate four-scan comparison with 2x original nuisance freedom."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT
from prepare_four_scan_comparison import OUTPUT
from loose_nuisance_model import fit_loose
from find_profile_minimum import local_offset

BASE=OUTPUT/'comparison-v2'
OUT=OUTPUT/'loose-nuisance-2x'


def run(index):
    import prepare_scans as prep
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from position_profile_grid import geodesic_position
    from joint_inputs import _coordinates
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from plot_all_glrt_doppler_overlay import serializable
    started=time.monotonic();parent=json.loads((BASE/'receipt.json').read_text())
    scan=parent['scans'][index-1];sid=scan['session'];prep.ROOT=OUTPUT
    directory=OUT/sid;directory.mkdir(parents=True,exist_ok=True)
    if (directory/'result.json').exists():raise FileExistsError('completed result already exists')
    hashes=snapshot_files([__file__,ROOT/'loose_nuisance_model.py',ROOT/'timing_model.py',ROOT/'rf_calibration_diagnostic.py',
        BASE/'receipt.json',OUTPUT/'selection.json'])
    def save(name,value):
        (directory/name).write_text(json.dumps(serializable(value),indent=2,allow_nan=False)+'\n')
    selection=json.loads((OUTPUT/'selection.json').read_text());pose=selection['poses'][index-1]
    assert pose['session']==sid
    lat,lon=pose['latitude'],pose['longitude'];center=geodesic_position(lat,lon,0,0)
    jac=np.column_stack([(geodesic_position(lat,lon,b,1)-geodesic_position(lat,lon,b+180,1))/2 for b in (90,0)])*100
    _,data=prep.load_scan(sid);bundle=OUTPUT/'scans'/sid
    seed=json.loads((bundle/'seed.json').read_text());manifest=json.loads((bundle/'bundle.json').read_text())
    hashes.update(snapshot_files([bundle/n for n in ('seed.json','bundle.json','bundle.npz')]))
    latest=ROOT/'later-tle-timing-aligned-v2/receipt.json';tle=Path(json.loads(latest.read_text())['latest_snapshot']['path'])
    hashes.update(snapshot_files([latest,tle]));catalogue=parse_element_sets(tle.read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)};sats=np.asarray(seed['satellites'])
    indices=[lookup[int(n)] for n in data.numbers[sats]]
    p,v,valid=propagate_candidate_states(catalogue,indices,manifest['origin_utc_ns'],data.nodes,np.array([0.]))
    assert list(valid)==indices
    data.position=data.position.copy();data.velocity=data.velocity.copy();data.position[sats]=p[:,0];data.velocity[sats]=v[:,0]
    probability=.8/len(sats);variants=[];cache={};evaluations=[]
    def sourcefit(e):
        i=scan['evaluations'].index(e);path=BASE/sid/f'fit-{i:04d}.json'
        hashes.update(snapshot_files([path]));return json.loads(path.read_text())
    for old in scan['variants']:
        key=tuple(old['policy']['kept']);threshold=old['threshold']
        if key in cache:
            variants.append(dict(cache[key],threshold=threshold));continue
        chosen=np.array([s for s in sats if int(data.numbers[s]) in key]);tag='off' if threshold is None else str(threshold)
        print('START',index,tag,key,flush=True)
        source=[e for e in scan['evaluations'] if tuple(e['candidates'])==key]
        roof_e=min((e for e in source if np.linalg.norm(np.asarray(e['position'])-center)<1e-8),key=lambda e:e['objective'])
        best_e=min(source,key=lambda e:abs(e['objective']-old['best']['objective'])+
                   1e6*np.linalg.norm(np.asarray(e['position'])-old['best']['position_km']))
        oldroof=sourcefit(roof_e);oldbest=sourcefit(best_e)
        def fitted(initial,position=None,start=None):
            f=fit_loose(data,initial,chosen,probability,center,fixed_position=position,start_position=start,budget_s=60.)
            n=len(evaluations);save(f'fit-{n:04d}.json',f)
            evaluations.append(dict(index=n,threshold=threshold,candidates=key,position_km=f['parameters'][:2],
                objective=f['objective'],success=f['success'],kkt_residual=f['kkt_residual']))
            save('evaluations.json',evaluations)
            if not f['success']:print('UNCONVERGED',index,tag,n,f['kkt_residual'],f['messages'],flush=True)
            return f
        zero=dict(oldroof,parameters=np.asarray(oldroof['parameters']).copy())
        zero['parameters'][6+chosen]=0.
        roof_trials=[fitted(oldroof,position=center),fitted(zero,position=center)]
        roof=min(roof_trials,key=lambda f:f['objective']);save(f'{tag}-roof.json',roof)
        attempts=[fitted(roof,start=center),fitted(oldbest,start=np.asarray(old['best']['position_km']))]
        best=min(attempts,key=lambda f:f['objective'])
        # Check the new minimum's nuisance basin back at the roof too.
        roof_check=fitted(best,position=center)
        if roof_check['objective']<roof['objective']-1e-6:
            roof=roof_check;save(f'{tag}-roof.json',roof)
            attempts.append(fitted(roof,start=center));best=min(attempts,key=lambda f:f['objective'])
        position=np.asarray(best['parameters'][:2]);en=local_offset(lat,lon,*_coordinates(position))
        boundary=bool(np.any(np.abs(position-center)>4.99))
        probes=[]
        for bearing in (90,270,0,180):
            f=fitted(roof,position=geodesic_position(lat,lon,bearing,10.))
            probes.append(f)
        fd=np.array([probes[0]['objective']-probes[1]['objective'],probes[2]['objective']-probes[3]['objective']])*5
        gradient=np.asarray(roof['free_position_gradient'])@jac
        neighbors=[]
        for dx,dy in ((.05,0),(-.05,0),(0,.05),(0,-.05)):
            f=fitted(best,position=position+[dx,dy])
            neighbors.append(dict(offset_km=[dx,dy],delta=f['objective']-best['objective'],success=f['success']))
        record=dict(threshold=threshold,policy=old['policy'],old_distance_m=old['best']['distance_m'],
            old_boundary=old['boundary'],old_roof_support=old['roof_support'],roof=roof,best=best,attempts=attempts,
            east_m=en[0],north_m=en[1],distance_m=float(np.linalg.norm(en)),boundary=boundary,
            delta_score=best['objective']-roof['objective'],roof_gradient_per_100m=gradient,
            roof_finite_difference_per_100m=fd,gradient_check=bool(np.allclose(gradient,fd,rtol=.03,atol=.01)),
            start_agreement_m=float(np.linalg.norm(np.asarray(attempts[0]['parameters'][:2])-attempts[1]['parameters'][:2])*1000),
            neighbors=neighbors,all_fits_converged=all(e['success'] for e in evaluations if e['threshold']==threshold))
        variants.append(record);cache[key]=record;save('partial.json',variants)
        print('RESULT',index,tag,'error_m',record['distance_m'],'boundary',boundary,'KKT',best['kkt_residual'],
              'active timing',best['common_bound_active'],best['individual_bound_active_count'],flush=True)
    assert_snapshot_unchanged(hashes)
    result=dict(scan_index=index,session=sid,variants=variants,evaluations=evaluations,source_hashes=hashes,
        elapsed_s=time.monotonic()-started,scope='Original candidate exclusions frozen; full GLRT-group likelihood and original '
        'per-candidate detection probability unchanged. Common N(0,20s) truncated +/-20s; each zero-sum relative satellite '
        'deviation has sigma 2s Gaussian quadratic penalty and no added hard bound. Total timing=common+deviation. '
        'RX slopes +/-100 Hz/s; common RF coefficient +/-10000 Hz/GHz; RX offsets remain unbounded. '
        'All finite nuisance bounds and prior widths are 2x ORIGINAL, not the tight experiment. Likelihood sigma remains 200 Hz. '
        'Joint constrained position/nuisance minimization, two starting points, same +/-5 regional-km '
        'position search box. Conditional roof gradients and neighbor probes refit nuisance under the new constraints. '
        'No new collection or production changes; no guarantee of global minima.')
    save('result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,required=True,choices=range(1,5))
    run(parser.parse_args().scan)
