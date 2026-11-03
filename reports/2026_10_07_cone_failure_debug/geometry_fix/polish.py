"""Predeclared matched 30 s polish of all six own selected gate candidates."""
import argparse,copy,importlib.util,json,sys,time
from pathlib import Path
from dataclasses import replace
import numpy as np
from objective import HERE,CONES,cones,GeometryObjective
sys.path.insert(0,str(CONES))
from experiment import loader,controls
from leo.contracts.regional_position import PositionScore
from leo.analysis.regional_position_score import PositionObjective,coordinates
from leo.analysis.regional_position_fit import fit_position

def run(case):
    path=HERE/case/'results.json';primary=json.loads(path.read_text());assert primary['status']=='complete'
    if (HERE/case/'polished.json').exists():raise FileExistsError('completed polish exists')
    begun=time.monotonic();doc,old,obs,prior,bank,checkpoint,prefix=loader.load(case)
    theta,frames,support=cones.cone_bundle();score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
    out=copy.deepcopy(primary);out.update(primary_selections=copy.deepcopy(primary['selections']),polish_runs=[],polish_protocol_sha256=controls.digest_bytes(Path(__file__).read_bytes()),polish_seconds_per_fit=30.,polish_maximum_iterations=600,status='polishing')
    for selected in primary['selections']:
        option=selected['option'];arm=selected['arm'];basin=selected['basin'];region=primary['basins'][basin];center=np.asarray(region['center']);radius=region['radius_km']
        assoc=checkpoint.get(prefix+':'+basin+':association')['result'];cal=checkpoint.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices']);baseline=np.asarray(cal['receiver_baseline_hz'])
        assert subset.numbers.tolist()==region['numbers'] and controls.vector_digest(baseline)==region['baseline_sha256']
        objective=GeometryObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,mode=option,theta=theta,frames=frames,support=support);base=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=baseline)
        seed=np.asarray(selected['vector']);assert abs(objective.evaluate(seed)[0]-selected['objective'])<1e-6
        for origin,r in ((center,radius),(np.zeros(2),prior.radius_km)):
            distance=np.linalg.norm(seed[:2]-origin)
            if distance>r:
                assert distance-r<1e-5;seed[:2]=origin+(seed[:2]-origin)*(r-1e-8)/distance
        fit=fit_position(objective,seed,rf_arm=arm,maximum_seconds=30,maximum_iterations=600,local_center=center,local_radius_km=radius)
        value,g,terms=objective.evaluate(fit.vector);uniform_value,_,uniform=base.evaluate(fit.vector);mass=float(terms.responsibilities.sum());uniform_mass=float(uniform.responsibilities.sum())
        row={'option':option,'arm':arm,'basin':basin,'origin':'selected-polish','vector':fit.vector.tolist(),'objective':float(value),'selection_score':float(value+selected['calibration_penalty']),'calibration_penalty':selected['calibration_penalty'],'data_nll':float(terms.nll),'uniform_frequency_data_nll':float(uniform.nll),'geometry_score_adjustment':float(value-uniform_value),'timing_penalty':float(value-terms.nll),'posterior_rms_hz':float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),'uniform_posterior_rms_hz':float(np.sqrt(np.sum(uniform.responsibilities*uniform.residual_hz**2)/uniform_mass)),'signal_mass':mass,'signal_fraction':mass/len(obs.window_ids),'mean_clutter_posterior':float(terms.clutter_probability.mean()),'elapsed_s':fit.elapsed_s,'stop_reason':fit.stop_reason,'evaluations':fit.evaluations,**controls.audit(fit.vector,g,objective.basis,arm,prior.radius_km,center,radius,max(-20.,subset.nodes_s[0]-obs.times_s.min()),min(20.,subset.nodes_s[-1]-obs.times_s.max()))}
        if option!='control':
            geom=objective.last_geometry;assert np.all(geom['q']<=geom['base_q']+1e-15)
            row.update(posterior_mean_cone_support=float(np.sum(terms.responsibilities*geom['support'])/mass),mean_row_q_mass=float(geom['q'].sum(axis=1).mean()),mean_row_base_q_mass=float(geom['base_q'].sum(axis=1).mean()))
        assert abs(row['objective']-fit.objective)<1e-6 and abs(row['stationarity']-fit.stationarity)<1e-5
        out['polish_runs'].append({'option':option,'arm':arm,'basin':basin,'seed_sha256':controls.vector_digest(selected['vector']),'result':row})
        if row['feasible']:out['candidates'].append(row)
        (HERE/case/'polish-progress.json').write_text(json.dumps(out,default=controls.encode,indent=2));print('POLISH',case,option,arm,row['selection_score'],row['converged'],flush=True)
    out['selections']=[min((r for r in out['candidates'] if r['option']==option and r['arm']==arm),key=lambda r:r['selection_score']) for option in primary['options'] for arm in controls.ARMS]
    for row in out['candidates']:
        lat,lon=np.radians(coordinates(prior,row['vector'][:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    out['nested_search_gaps']={option:max(0.,next(r['selection_score'] for r in out['selections'] if r['option']==option and r['arm']=='fitted-c')-next(r['selection_score'] for r in out['selections'] if r['option']==option and r['arm']=='zero-c')) for option in primary['options']}
    out.update(status='complete',polish_elapsed_s=time.monotonic()-begun,polish_fit_elapsed_s=sum(q['result']['elapsed_s'] for q in out['polish_runs']))
    (HERE/case/'polished.json').write_text(json.dumps(out,default=controls.encode,indent=2))
    for row in out['selections']:print('SELECTED',case,row['option'],row['arm'],row['horizontal_error_m'],row['converged'],row['boundary'],row['selection_score'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('1939','2139'),required=True);run(parser.parse_args().case)
