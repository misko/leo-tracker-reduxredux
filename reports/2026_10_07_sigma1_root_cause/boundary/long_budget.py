"""Own-arm 60-second continuation at sigma1 and unchanged original constraints."""
import json
from pathlib import Path
from dataclasses import replace,asdict
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
from experiment import HERE,REPORTS,controls,gradient_details

def main():
    r=json.loads((HERE/'results.json').read_text());snap=json.loads((REPORTS/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(c['regional_document'] for c in snap['captures'] if c['session_id']==r['session_id'])
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:source=store.load(r['session_id'])
    finally:store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256'] and source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prep=prepare_position_windows(source);obs=prep.observations
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));ref=next(x for x in archive.list_snapshots() if x.digest==doc['diagnostics']['snapshot_sha256'] and x.collected_utc_ns==doc['diagnostics']['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(ref));cat=parse_element_sets(payload)
    ix=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);prior=RegionalPrior(**doc['configuration']['prior'])
    assert canonical_digest({'windows':prep.evidence_sha256,'tle':ref.digest,'candidates':[int(cat.satellite_numbers[i]) for i in ix]})==doc['evidence_sha256']
    bank,receipt=build_regional_bank(cat,ix,prep.start_utc_ns,obs,prior,maximum_seconds=60)
    assert list(receipt.retained_numbers)==doc['diagnostics']['bank']['retained_numbers']
    checkpoints=RegionalCheckpointStore(Path('/srv/bulk/leo'),r['session_id'],doc['diagnostics']['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])
    output={'sigma_s':1.0,'maximum_seconds':60,'maximum_iterations':1000,'domain':'original','session_id':r['session_id'],'runs':[]}
    for arm in ('fitted-c','zero-c'):
        start=next(q for q in r['selections'] if q['domain']=='original' and q['arm']==arm);basin=start['basin']
        cal=checkpoints.get(prefix+':'+basin+':calibration')['result'];assoc=checkpoints.get(prefix+':'+basin+':association')['result']
        subset=bank.select(assoc['selected_indices']);objective=PositionObjective(obs,subset,prior,replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
        seed=np.asarray(start['vector']);center=np.asarray(r['basins'][basin]['center']);radius=r['basins'][basin]['radius_km'];distance=np.linalg.norm(seed[:2]-center)
        if distance>radius:
            assert distance-radius<1e-5;seed[:2]=center+(seed[:2]-center)*(radius-1e-8)/distance
        initial=objective.evaluate(seed)[0];assert abs(initial-start['objective'])<1e-5
        fit=fit_position(objective,seed,rf_arm=arm,maximum_seconds=60,maximum_iterations=1000,local_center=center,local_radius_km=radius)
        value,g,terms=objective.evaluate(fit.vector)
        minimum=max(-20.,subset.nodes_s[0]-obs.times_s.min());maximum=min(20.,subset.nodes_s[-1]-obs.times_s.max())
        audited=controls.audit(fit.vector,g,objective.basis,arm,250,center,radius,minimum,maximum)
        assert abs(audited['stationarity']-fit.stationarity)<1e-5 and audited['feasible']
        lat,lon=np.radians(coordinates(prior,fit.vector[:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        result={'arm':arm,'basin':basin,'start':start,'initial_objective':float(initial),'selection_score':float(value+start['calibration_penalty']),'horizontal_error_m':float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1)))),'data_nll':float(terms.nll),'relative_penalty':float(.5*np.sum(fit.vector[8:]**2)),**asdict(fit),**gradient_details(fit.vector,g,center,radius),'independent_audit':audited}
        output['runs'].append(result);(HERE/'long_budget.json').write_text(json.dumps(output,default=controls.encode,indent=2));print(arm,result['selection_score'],result['horizontal_error_m'],fit.stationarity,fit.stop_reason,fit.elapsed_s,flush=True)

if __name__=='__main__':main()
