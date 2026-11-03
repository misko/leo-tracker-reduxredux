"""Matched secondary polish of own selected cone candidates; preserve primaries."""
import argparse
import copy
from dataclasses import replace
import json
from pathlib import Path
import time
import numpy as np
from experiment import HERE,loader,controls,OPTIONS
from cone_objective import ConeObjective,cone_bundle
from leo.analysis.regional_position_score import PositionObjective,coordinates
from leo.analysis.regional_position_fit import fit_position
from leo.contracts.regional_position import PositionScore

def run(case):
    path=HERE/case/'results.json';primary=json.loads(path.read_text())
    assert primary['status']=='complete'
    destination=HERE/case/'polished.json'
    if destination.exists():raise FileExistsError('completed polish already exists')
    begun=time.monotonic();doc,old,obs,prior,bank,checkpoints,prefix=loader.load(case)
    assert primary['evidence_sha256']==doc['evidence_sha256']
    assert primary['objective_sha256']==controls.digest_bytes((HERE/'cone_objective.py').read_bytes())
    theta,frames,support=cone_bundle();score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
    output=copy.deepcopy(primary);output.update(primary_selections=copy.deepcopy(primary['selections']),polish_runs=[],primary_receipt_sha256=controls.digest_bytes(path.read_bytes()),polish_protocol_sha256=controls.digest_bytes(Path(__file__).read_bytes()),polish_seconds_per_fit=30.,polish_maximum_iterations=600,status='polishing')
    for option,strength in OPTIONS.items():
        for arm in controls.ARMS:
            selected=next(r for r in primary['selections'] if r['option']==option and r['arm']==arm)
            basin=selected['basin'];region=primary['basins'][basin];center=np.asarray(region['center']);radius=region['radius_km']
            association=checkpoints.get(prefix+':'+basin+':association')['result'];calibration=checkpoints.get(prefix+':'+basin+':calibration')['result']
            subset=bank.select(association['selected_indices']);assert subset.numbers.tolist()==region['numbers']
            baseline=np.asarray(calibration['receiver_baseline_hz']);assert controls.vector_digest(baseline)==region['baseline_sha256']
            objective=ConeObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,strength=strength,theta=theta,frames=frames,support=support)
            base=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=baseline)
            seed=np.asarray(selected['vector']).copy();assert abs(objective.evaluate(seed)[0]-selected['objective'])<1e-6
            repairs=[]
            for origin,r in ((center,radius),(np.zeros(2),prior.radius_km)):
                distance=np.linalg.norm(seed[:2]-origin)
                if distance>r:
                    assert distance-r<1e-5
                    repairs.append(float(distance-r));seed[:2]=origin+(seed[:2]-origin)*(r-1e-8)/distance
            fit=fit_position(objective,seed,rf_arm=arm,maximum_seconds=30.,maximum_iterations=600,local_center=center,local_radius_km=radius)
            value,g,terms=objective.evaluate(fit.vector);uniform_value,_,uniform=base.evaluate(fit.vector)
            mass=float(terms.responsibilities.sum());uniform_mass=float(uniform.responsibilities.sum())
            row=dict(option=option,strength=strength,arm=arm,basin=basin,origin='selected-polish',vector=fit.vector.tolist(),objective=float(value),selection_score=float(value+selected['calibration_penalty']),calibration_penalty=selected['calibration_penalty'],data_nll=float(terms.nll),uniform_frequency_data_nll=float(uniform.nll),cone_score_adjustment=float(value-uniform_value),timing_penalty=float(value-terms.nll),posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),uniform_posterior_rms_hz=float(np.sqrt(np.sum(uniform.responsibilities*uniform.residual_hz**2)/uniform_mass)),signal_mass=mass,signal_fraction=mass/len(obs.window_ids),elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason,evaluations=fit.evaluations,**controls.audit(fit.vector,g,objective.basis,arm,prior.radius_km,center,radius,max(-20.,subset.nodes_s[0]-obs.times_s.min()),min(20.,subset.nodes_s[-1]-obs.times_s.max())))
            if strength:
                geom=objective.last_geometry;np.testing.assert_allclose(geom['q'].sum(axis=1),geom['base_q'].sum(axis=1),rtol=1e-12,atol=1e-12)
                row['posterior_mean_cone_support']=float(np.sum(terms.responsibilities*geom['support'])/mass)
            assert abs(row['objective']-fit.objective)<1e-6 and abs(row['stationarity']-fit.stationarity)<1e-5
            output['polish_runs'].append(dict(option=option,arm=arm,basin=basin,seed_sha256=controls.vector_digest(selected['vector']),spatial_rounding_repairs_km=repairs,result=row))
            if row['feasible']:output['candidates'].append(row)
            (HERE/case/'polish-progress.json').write_text(json.dumps(output,indent=2,default=controls.encode))
            print('POLISH',case,option,arm,row['selection_score'],row['converged'],row['elapsed_s'],flush=True)
    output['selections']=[min((r for r in output['candidates'] if r['option']==option and r['arm']==arm),key=lambda r:r['selection_score']) for option in OPTIONS for arm in controls.ARMS]
    # Truth is evaluated only after final score-only selection.
    for row in output['candidates']:
        lat,lon=np.radians(coordinates(prior,row['vector'][:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    output['nested_search_gaps']={option:max(0.,next(r['selection_score'] for r in output['selections'] if r['option']==option and r['arm']=='fitted-c')-next(r['selection_score'] for r in output['selections'] if r['option']==option and r['arm']=='zero-c')) for option in OPTIONS}
    output.update(status='complete',total_polish_elapsed_s=time.monotonic()-begun,total_polish_fit_elapsed_s=sum(q['result']['elapsed_s'] for q in output['polish_runs']))
    destination.write_text(json.dumps(output,indent=2,default=controls.encode))
    for row in output['selections']:print('SELECTED',case,row['option'],row['arm'],row['horizontal_error_m'],row['converged'],row['boundary'],row['selection_score'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=['2139','1939'],required=True);run(parser.parse_args().case)
