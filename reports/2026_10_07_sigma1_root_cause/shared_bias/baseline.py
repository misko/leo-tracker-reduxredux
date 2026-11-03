"""Matched correction-on/off intervention; retain affine baseline exactly."""
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
from experiment import HERE,REPORTS,SID,options

def correction_off_seed(vector,design,correction):
    v=np.asarray(vector,float).copy();affine=np.linalg.lstsq(design[:,:4],correction,rcond=None)[0];v[2:6]+=affine
    return v,affine

def main():
    import leo
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective,coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import RegionalPrior,PositionScore
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
    snapshot=json.loads((REPORTS/'2026_10_07_recent_filter_review/snapshot.json').read_text());doc=next(c['regional_document'] for c in snapshot['captures'] if c['session_id']==SID);saved=doc['diagnostics']
    for relative,expected in doc['configuration']['source_digests'].items():assert options.digest_bytes((Path(leo.__file__).parent/relative).read_bytes())==expected
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:source=store.load(SID)
    finally:store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256'];assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prepared=prepare_position_windows(source);obs=prepared.observations
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));tle=next(s for s in archive.list_snapshots() if s.digest==saved['snapshot_sha256'] and s.collected_utc_ns==saved['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(tle));catalogue=parse_element_sets(payload);indices=np.asarray([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')]);evidence=canonical_digest(dict(windows=prepared.evidence_sha256,tle=tle.digest,candidates=[int(catalogue.satellite_numbers[i]) for i in indices]));assert evidence==doc['evidence_sha256']
    prior=RegionalPrior(**doc['configuration']['prior']);bank,receipt=build_regional_bank(catalogue,indices,prepared.start_utc_ns,obs,prior,maximum_seconds=60);assert list(receipt.retained_numbers)==saved['bank']['retained_numbers']
    previous=json.loads((HERE/'results.json').read_text());basin=previous['selected']['fitted-c']['basin'];assert basin==previous['selected']['zero-c']['basin'];meta=previous['basins'][basin]
    cp=RegionalCheckpointStore(Path('/srv/bulk/leo'),SID,saved['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])+':'+basin;cal=cp.get(prefix+':calibration')['result'];assoc=cp.get(prefix+':association')['result'];bank=bank.select(assoc['selected_indices'])
    score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.);baseline=np.asarray(cal['receiver_baseline_hz']);correction=np.asarray(cal['correction']['values_hz']);assert baseline.shape==correction.shape
    on=PositionObjective(obs,bank,prior,score,receiver_baseline_hz=baseline);off=PositionObjective(obs,bank,prior,score,receiver_baseline_hz=baseline-correction)
    affine_coeff=np.linalg.lstsq(on.design[:,:4],baseline-correction,rcond=None)[0];assert np.max(np.abs(on.design[:,:4]@affine_coeff-(baseline-correction)))<1e-6
    out=dict(session_id=SID,basin=basin,sigma_s=1.,bank_numbers=bank.numbers.tolist(),correction_by_receiver={str(rx):dict(min_hz=float(correction[obs.receiver==rx].min()),max_hz=float(correction[obs.receiver==rx].max()),rms_hz=float(np.sqrt(np.mean(correction[obs.receiver==rx]**2)))) for rx in (0,1)},rows=[])
    for arm in options.ARMS:
        selected=previous['selected'][arm];v=np.asarray(selected['vector']);assert abs(on.evaluate(v)[0]-selected['objective'])<1e-6
        for label,obj in [('on',on),('off',off)]:
            seed=v.copy();affine=np.zeros(4)
            if label=='off':seed,affine=correction_off_seed(seed,on.design,correction)
            fit=fit_position(obj,seed,rf_arm=arm,maximum_seconds=12,maximum_iterations=300,local_center=np.asarray(meta['center']),local_radius_km=meta['radius_km']);value,grad,terms=obj.evaluate(fit.vector);audit=options.audit(fit.vector,grad,obj.basis,arm,prior.radius_km,np.asarray(meta['center']),meta['radius_km'],max(-20.,bank.nodes_s[0]-obs.times_s.min()),min(20.,bank.nodes_s[-1]-obs.times_s.max()));mass=terms.responsibilities.sum()
            lat,lon=coordinates(prior,fit.vector[:2]);a,b=np.radians([lat,lon]);a0,b0=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((a-a0)/2)**2+np.cos(a)*np.cos(a0)*np.sin((b-b0)/2)**2
            row=dict(arm=arm,correction=label,objective=value,data_nll=terms.nll,relative_penalty=.5*np.sum((obj.basis@fit.vector[8:])**2),common_penalty=.5*(fit.vector[7]/3.)**2,rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),error_m=float(6371008.8*2*np.arctan2(np.sqrt(h),np.sqrt(1-h))),vector=fit.vector.tolist(),seed_affine_adjustment=affine.tolist(),initial_prediction_change_rms_hz=float(np.sqrt(np.mean((correction-on.design[:,:4]@affine)**2))) if label=='off' else 0.,**audit,elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason);out['rows'].append(row);(HERE/'baseline_results.json').write_text(json.dumps(out,indent=2));print(json.dumps(row),flush=True)
    out['total_fit_elapsed_s']=sum(r['elapsed_s'] for r in out['rows']);(HERE/'baseline_results.json').write_text(json.dumps(out,indent=2))

if __name__=='__main__':main()
