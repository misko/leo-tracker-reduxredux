"""Predeclared all-basin geometry-gate comparison, original truth-free seeds."""
import argparse,json,sys,time
from dataclasses import replace
from pathlib import Path
import numpy as np
from objective import HERE,CONES,cones,GeometryObjective
sys.path.insert(0,str(CONES))
from experiment import loader,controls
from leo.contracts.regional_position import PositionScore
from leo.analysis.regional_position_score import PositionObjective,coordinates
from leo.analysis.regional_position_fit import fit_position

OPTIONS=('control','conditional','absolute2')

def run(case):
    destination=HERE/case;destination.mkdir(exist_ok=True)
    if (destination/'results.json').exists():raise FileExistsError('completed receipt already exists')
    begun=time.monotonic();doc,old,obs,prior,bank,checkpoint,prefix=loader.load(case)
    source=CONES/case/'polished.json';primary=json.loads(source.read_text())
    theta,frames,support=cones.cone_bundle();score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
    pool=[r for r in primary['candidates'] if r['option']=='control']
    output={'case':case,'session_id':old['session_id'],'options':list(OPTIONS),'sigma_s':1.,'seconds_per_fit':15.,'maximum_iterations':400,'source_receipt_sha256':controls.digest_bytes(source.read_bytes()),'objective_sha256':controls.digest_bytes((HERE/'objective.py').read_bytes()),'protocol_sha256':controls.digest_bytes(Path(__file__).read_bytes()),'cone_digests':cones.CONE_BUNDLE_DIGESTS,'input_sha256':doc['input_manifest_sha256'],'analysis_sha256':doc['analysis_manifest_sha256'],'evidence_sha256':doc['evidence_sha256'],'basins':primary['basins'],'runs':[],'candidates':[],'selections':[],'status':'running'}
    def save(): (destination/'progress.json').write_text(json.dumps(output,default=controls.encode,indent=2))
    for basin,region in primary['basins'].items():
        center=np.asarray(region['center']);radius=region['radius_km']
        assoc=checkpoint.get(prefix+':'+basin+':association')['result'];cal=checkpoint.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices']);baseline=np.asarray(cal['receiver_baseline_hz'])
        assert subset.numbers.tolist()==region['numbers'] and controls.vector_digest(baseline)==region['baseline_sha256']
        rows=[r for r in pool if r['basin']==basin];penalty=rows[0]['calibration_penalty'];base=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=baseline)
        for r in rows:assert abs(base.evaluate(np.asarray(r['vector']))[0]-r['objective'])<1e-6
        seeds={arm:min((r for r in rows if r['arm']==arm),key=lambda r:r['objective']) for arm in controls.ARMS}
        minimum=max(-20.,subset.nodes_s[0]-obs.times_s.min());maximum=min(20.,subset.nodes_s[-1]-obs.times_s.max())
        for option in OPTIONS:
            objective=GeometryObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,mode=option,theta=theta,frames=frames,support=support)
            def record(vector,arm,origin,**extra):
                value,g,terms=objective.evaluate(vector);uniform_value,_,uniform=base.evaluate(vector);mass=float(terms.responsibilities.sum());uniform_mass=float(uniform.responsibilities.sum())
                row={'option':option,'arm':arm,'basin':basin,'origin':origin,'vector':vector.tolist(),'objective':float(value),'selection_score':float(value+penalty),'calibration_penalty':penalty,'data_nll':float(terms.nll),'uniform_frequency_data_nll':float(uniform.nll),'geometry_score_adjustment':float(value-uniform_value),'timing_penalty':float(value-terms.nll),'posterior_rms_hz':float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),'uniform_posterior_rms_hz':float(np.sqrt(np.sum(uniform.responsibilities*uniform.residual_hz**2)/uniform_mass)),'signal_mass':mass,'signal_fraction':mass/len(obs.window_ids),'mean_clutter_posterior':float(terms.clutter_probability.mean()),**controls.audit(vector,g,objective.basis,arm,prior.radius_km,center,radius,minimum,maximum),**extra}
                if option!='control':
                    geom=objective.last_geometry;assert np.all(geom['q']<=geom['base_q']+1e-15)
                    row.update(posterior_mean_cone_support=float(np.sum(terms.responsibilities*geom['support'])/mass),mean_row_q_mass=float(geom['q'].sum(axis=1).mean()),mean_row_base_q_mass=float(geom['base_q'].sum(axis=1).mean()))
                return row
            for r in rows:
                incumbent=record(np.asarray(r['vector']),r['arm'],'saved-no-cone:'+r['origin'])
                if incumbent['feasible']:output['candidates'].append(incumbent)
            for arm in controls.ARMS:
                seed=np.asarray(seeds[arm]['vector']).copy()
                for origin,r in ((center,radius),(np.zeros(2),prior.radius_km)):
                    distance=np.linalg.norm(seed[:2]-origin)
                    if distance>r:
                        assert distance-r<1e-5;seed[:2]=origin+(seed[:2]-origin)*(r-1e-8)/distance
                fit=fit_position(objective,seed,rf_arm=arm,maximum_seconds=15,maximum_iterations=400,local_center=center,local_radius_km=radius)
                result=record(fit.vector,arm,'continued',elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason,evaluations=fit.evaluations)
                assert abs(result['objective']-fit.objective)<1e-6 and abs(result['stationarity']-fit.stationarity)<1e-5
                output['runs'].append({'option':option,'arm':arm,'basin':basin,'seed_sha256':controls.vector_digest(seeds[arm]['vector']),'result':result})
                if result['feasible']:output['candidates'].append(result)
                save();print(case,basin,option,arm,result['selection_score'],result['converged'],flush=True)
    output['selections']=[min((r for r in output['candidates'] if r['option']==option and r['arm']==arm),key=lambda r:r['selection_score']) for option in OPTIONS for arm in controls.ARMS]
    for row in output['candidates']:
        lat,lon=np.radians(coordinates(prior,row['vector'][:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    output['nested_search_gaps']={option:max(0.,next(r['selection_score'] for r in output['selections'] if r['option']==option and r['arm']=='fitted-c')-next(r['selection_score'] for r in output['selections'] if r['option']==option and r['arm']=='zero-c')) for option in OPTIONS}
    output.update(status='complete',elapsed_s=time.monotonic()-begun);save();(destination/'results.json').write_text(json.dumps(output,indent=2,default=controls.encode))
    for r in output['selections']:print('SELECTED',case,r['option'],r['arm'],r['horizontal_error_m'],r['converged'],r['boundary'],r['selection_score'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('1939','2139'),required=True);run(parser.parse_args().case)
