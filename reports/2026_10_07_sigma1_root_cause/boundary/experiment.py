"""Frozen sigma=1 all-basin disk and boundary-seed diagnostics; read-only ports."""
import importlib.util
import json
from pathlib import Path
from dataclasses import replace
import time
import numpy as np
from leo.analysis.regional_position_score import PositionObjective,coordinates
from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import RegionalPrior,PositionScore
from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent.parent
spec=importlib.util.spec_from_file_location('controls',REPORTS/'2026_10_07_bad_sample_options/experiment.py')
controls=importlib.util.module_from_spec(spec);spec.loader.exec_module(controls)

def gradient_details(vector,gradient,center,radius):
    radial=(vector[:2]-center)/np.linalg.norm(vector[:2]-center)
    tangential=np.array([-radial[1],radial[0]])
    scales=np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(len(vector)-7)]
    return {'local_disk_slack_km2':float(radius**2-np.sum((vector[:2]-center)**2)),
            'prior_disk_slack_km2':float(250**2-np.sum(vector[:2]**2)),
            'radial_derivative_per_km':float(gradient[:2]@radial),
            'tangential_derivative_per_km':float(gradient[:2]@tangential),
            'scaled_gradient':(gradient*scales).tolist(),
            'largest_scaled_gradient_index':int(np.argmax(abs(gradient*scales))),
            'nuisance_scaled_gradient_max':float(np.max(abs((gradient*scales)[2:])))}

def main():
    started=time.monotonic()
    previous=json.loads((REPORTS/'2026_10_07_bad_sample_options/2139/results.json').read_text())
    snapshot=json.loads((REPORTS/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(c['regional_document'] for c in snapshot['captures'] if c['session_id']==previous['session_id'])
    root=Path('/srv/bulk/leo'); store=ScannerTrackingInputStore(root)
    try:source=store.load(previous['session_id'])
    finally:store.close()
    assert source.input_manifest_sha256==previous['input_sha256'] and source.analysis_manifest_sha256==previous['analysis_sha256']
    prepared=prepare_position_windows(source);obs=prepared.observations
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    ref=next(r for r in archive.list_snapshots() if r.digest==previous['tle_sha256'] and r.collected_utc_ns==doc['diagnostics']['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(ref));cat=parse_element_sets(payload)
    indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')])
    assert canonical_digest({'windows':prepared.evidence_sha256,'tle':ref.digest,'candidates':[int(cat.satellite_numbers[i]) for i in indices]})==doc['evidence_sha256']
    prior=RegionalPrior(**doc['configuration']['prior'])
    bank,receipt=build_regional_bank(cat,indices,prepared.start_utc_ns,obs,prior,maximum_seconds=60)
    assert list(receipt.retained_numbers)==doc['diagnostics']['bank']['retained_numbers']
    checkpoints=RegionalCheckpointStore(root,previous['session_id'],doc['diagnostics']['checkpoint_binding'])
    prefix=canonical_digest(doc['configuration']['run'])
    out={'sigma_s':1.0,'session_id':previous['session_id'],'maximum_seconds':12,'maximum_iterations':300,'runs':[],'candidates':[],'basins':previous['basins'],'original_sigma1_selections':previous['selections'],'diagnostics':[]}
    objectives={}
    def candidate(objective,vector,arm,basin,domain,origin,**extra):
        center=np.asarray(previous['basins'][basin]['center']);original=previous['basins'][basin]['radius_km']
        radius=original if domain=='original' else max(25,original*2)
        value,gradient,terms=objective.evaluate(vector)
        minimum=max(-20.,objective.bank.nodes_s[0]-obs.times_s.min());maximum=min(20.,objective.bank.nodes_s[-1]-obs.times_s.max())
        audit=controls.audit(vector,gradient,objective.basis,arm,250,center,radius,minimum,maximum)
        penalty=next(r['calibration_penalty'] for r in previous['candidates'] if r['basin']==basin)
        mass=float(terms.responsibilities.sum())
        return {'domain':domain,'arm':arm,'basin':basin,'origin':origin,'vector':vector.tolist(),'objective':float(value),'selection_score':float(value+penalty),'data_nll':float(terms.nll),'relative_penalty':float(.5*np.sum(vector[8:]**2)),'common_penalty':float(.5*(vector[7]/objective.score.common_sigma_s)**2),'calibration_penalty':penalty,'rms_hz':float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),'signal_mass':mass,**audit,**gradient_details(vector,gradient,center,radius),**extra}
    def run_fit(objective,seed,arm,basin,domain,origin):
        center=np.asarray(previous['basins'][basin]['center']);radius=previous['basins'][basin]['radius_km'] if domain=='original' else max(25,previous['basins'][basin]['radius_km']*2)
        seed=seed.copy()
        dist=np.linalg.norm(seed[:2]-center)
        if dist>radius:
            assert dist-radius<1e-5
            seed[:2]=center+(seed[:2]-center)*(radius-1e-8)/dist
        before=candidate(objective,seed,arm,basin,domain,origin+'-start')
        fit=fit_position(objective,seed,rf_arm=arm,maximum_seconds=12,maximum_iterations=300,local_center=center,local_radius_km=radius)
        result=candidate(objective,fit.vector,arm,basin,domain,origin,stop_reason=fit.stop_reason,evaluations=fit.evaluations,elapsed_s=fit.elapsed_s)
        assert abs(result['objective']-fit.objective)<1e-6 and abs(result['stationarity']-fit.stationarity)<1e-5
        out['runs'].append({'start':before,'result':result});out['candidates'].append(result)
        (HERE/'progress.json').write_text(json.dumps(out,default=controls.encode,indent=2))
        print(basin,arm,domain,origin,result['selection_score'],result['stationarity'],flush=True)
    for basin in sorted(previous['basins']):
        cal=checkpoints.get(prefix+':'+basin+':calibration')['result'];assoc=checkpoints.get(prefix+':'+basin+':association')['result']
        objective=PositionObjective(obs,bank.select(assoc['selected_indices']),prior,replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
        objectives[basin]=objective
        for row in previous['candidates']:
            if row['basin']==basin and row['option']=='sigma100':
                for domain in ('original','expanded'):
                    incumbent=candidate(objective,np.asarray(row['vector']),row['arm'],basin,domain,'sigma1-incumbent-'+row['origin'])
                    assert abs(incumbent['selection_score']-row['selection_score'])<1e-6
                    out['candidates'].append(incumbent)
        for arm in ('fitted-c','zero-c'):
            for saved in doc['diagnostics']['final_starts']:
                if saved['method']=='V16' and saved['basin']==basin and saved['arm']==arm and saved['fit']:
                    for domain in ('original','expanded'):
                        run_fit(objective,np.asarray(saved['fit']['vector']),arm,basin,domain,'original-'+saved['start'])
    # Boundary-start numerical probe: own sigma1 winner moved 1 metre inward.
    for arm in ('fitted-c','zero-c'):
        winner=next(r for r in previous['selections'] if r['option']=='sigma100' and r['arm']==arm)
        basin=winner['basin'];center=np.asarray(previous['basins'][basin]['center'])
        seed=np.asarray(winner['vector']);delta=seed[:2]-center;seed[:2]=center+delta*(np.linalg.norm(delta)-.001)/np.linalg.norm(delta)
        for domain in ('original','expanded'):run_fit(objectives[basin],seed,arm,basin,domain,'inward-1m-probe')
    selections=[]
    for domain in ('original','expanded'):
        for arm in ('fitted-c','zero-c'):
            selections.append(min((r for r in out['candidates'] if r['domain']==domain and r['arm']==arm and r['feasible']),key=lambda r:r['selection_score']))
    # Evaluate location after score selection.
    for row in out['candidates']:
        lat,lon=np.radians(coordinates(prior,row['vector'][:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']])
        h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    out.update(selections=selections,elapsed_s=time.monotonic()-started,status='complete')
    (HERE/'results.json').write_text(json.dumps(out,default=controls.encode,indent=2))
    for row in selections:print('SELECTED',row['domain'],row['arm'],row['basin'],row['origin'],row['selection_score'],row['horizontal_error_m'],row['converged'],flush=True)

if __name__=='__main__':main()
