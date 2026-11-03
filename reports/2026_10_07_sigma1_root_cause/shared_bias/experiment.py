"""Own-arm branch repair and conditional block diagnosis at V16 sigma=1s."""
import importlib.util
import json
from dataclasses import replace,fields
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
SID='scan-fw-6a376b600fc2f542'
spec=importlib.util.spec_from_file_location('options',REPORTS/'2026_10_07_bad_sample_options/experiment.py')
options=importlib.util.module_from_spec(spec);spec.loader.exec_module(options)

def subset(obs,mask):
    from leo.contracts.regional_position import PositionObservations
    return PositionObservations(**{f.name:tuple(np.asarray(obs.window_ids)[mask]) if f.name=='window_ids' else getattr(obs,f.name)[mask] for f in fields(obs)})

def choose(rows,arm):
    return min((r for r in rows if r['arm']==arm and r['feasible']),key=lambda r:(r['selection_score'],r['basin'],r['origin']))

def main():
    import leo
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective,coordinates,predict_orbits
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
    payload,_=exclude_labelled_starlink_debris(archive.read(tle));catalogue=parse_element_sets(payload)
    indices=np.asarray([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')]);evidence=canonical_digest(dict(windows=prepared.evidence_sha256,tle=tle.digest,candidates=[int(catalogue.satellite_numbers[i]) for i in indices]));assert evidence==doc['evidence_sha256']
    prior=RegionalPrior(**doc['configuration']['prior']);bank,receipt=build_regional_bank(catalogue,indices,prepared.start_utc_ns,obs,prior,maximum_seconds=60);assert list(receipt.retained_numbers)==saved['bank']['retained_numbers']
    cp=RegionalCheckpointStore(Path('/srv/bulk/leo'),SID,saved['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])
    old=json.loads((REPORTS/'2026_10_07_bad_sample_options/1939/results.json').read_text());finals=[r for r in saved['final_starts'] if r['method']=='V16' and r['fit']]
    output=dict(session_id=SID,verification=dict(input=source.input_manifest_sha256,analysis=source.analysis_manifest_sha256,evidence=evidence,tle=tle.digest,source_digests=True),sigma_s=1.,seconds_per_fit=12,iterations=300,rows=[],block_rows=[],diagnostics={},basins={},status='running');objectives={}
    def save(): (HERE/'results.json').write_text(json.dumps(output,default=options.encode,indent=2))
    def candidate(obj,vector,arm,basin,origin,penalty,meta,fit=None):
        vector=np.asarray(vector);value,grad,terms=obj.evaluate(vector);mass=terms.responsibilities.sum();center=np.asarray(meta['center']);radius=meta['radius_km']
        audit=options.audit(vector,grad,obj.basis,arm,prior.radius_km,center,radius,max(-20.,obj.bank.nodes_s[0]-obj.observations.times_s.min()),min(20.,obj.bank.nodes_s[-1]-obj.observations.times_s.max()))
        return dict(arm=arm,basin=basin,origin=origin,vector=vector.tolist(),objective=value,selection_score=value+penalty,calibration_penalty=penalty,data_nll=terms.nll,common_penalty=.5*(vector[7]/obj.score.common_sigma_s)**2,relative_penalty=.5*np.sum((obj.basis@vector[8:])**2),rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),signal_mass=float(mass),**audit,elapsed_s=fit.elapsed_s if fit else 0.,stop_reason=fit.stop_reason if fit else 'incumbent')
    for basin,meta in old['basins'].items():
        cal=cp.get(prefix+':'+basin+':calibration')['result'];assoc=cp.get(prefix+':'+basin+':association')['result'];subbank=bank.select(assoc['selected_indices']);assert subbank.numbers.tolist()==meta['numbers']
        score=PositionScore(**doc['configuration']['scores']['V16']);original=PositionObjective(obs,subbank,prior,score,receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']));obj=PositionObjective(obs,subbank,prior,replace(score,relative_sigma_s=1.),receiver_baseline_hz=original.baseline);objectives[basin]=obj;output['basins'][basin]=meta
        for r in [r for r in finals if r['basin']==basin]:
            assert abs(original.evaluate(np.asarray(r['fit']['vector']))[0]-r['fit']['objective'])<1e-6
            row=candidate(obj,r['fit']['vector'],r['arm'],basin,'saved-'+r['start'],r['calibration_penalty'],meta);output['rows'].append(row)
            start=np.asarray(r['fit']['vector']).copy()
            for origin,radius in ((np.zeros(2),prior.radius_km),(np.asarray(meta['center']),meta['radius_km'])):
                distance=np.linalg.norm(start[:2]-origin)
                if distance>radius:
                    assert distance-radius<1e-5;start[:2]=origin+(start[:2]-origin)*(radius-1e-8)/distance
            fit=fit_position(obj,start,rf_arm=r['arm'],maximum_seconds=12,maximum_iterations=300,local_center=np.asarray(meta['center']),local_radius_km=meta['radius_km'])
            row=candidate(obj,fit.vector,r['arm'],basin,'refined-'+r['start'],r['calibration_penalty'],meta,fit);output['rows'].append(row);print(basin,r['arm'],r['start'],row['selection_score'],row['stationarity'],flush=True);save()
    selected={arm:choose(output['rows'],arm) for arm in options.ARMS};output['selected']=selected
    # Truth is consulted only after objective-based full-scan selections are fixed.
    def add_error(row):
        lat,lon=coordinates(prior,row['vector'][:2]);a,b=np.radians([lat,lon]);a0,b0=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((a-a0)/2)**2+np.cos(a)*np.cos(a0)*np.sin((b-b0)/2)**2;row['error_m']=float(6371008.8*2*np.arctan2(np.sqrt(h),np.sqrt(1-h)))
    for row in output['rows']:add_error(row)
    save()
    masks={'rx0':obs.receiver==0,'rx1':obs.receiver==1,'early':obs.times_s<=obs.time_center_s,'late':obs.times_s>obs.time_center_s}
    for arm in options.ARMS:
        winner=selected[arm];basin=winner['basin'];obj=objectives[basin];v=np.asarray(winner['vector']);_,_,terms=obj.evaluate(v);_,_,spatial,_=predict_orbits(obj.bank,obs,prior,v[:2],v[7]+obj.basis@v[8:]);groups={**masks,**{f'channel{c}':obs.channel==c for c in np.unique(obs.channel)}}
        output['diagnostics'][arm]=dict(baseline_by_receiver={str(rx):dict(min=float(obj.baseline[obs.receiver==rx].min()),max=float(obj.baseline[obs.receiver==rx].max()),mean=float(obj.baseline[obs.receiver==rx].mean())) for rx in (0,1)},blocks={k:dict(windows=int(m.sum()),mass=float(terms.responsibilities[m].sum()),rms_hz=float(np.sqrt(np.sum(terms.responsibilities[m]*terms.residual_hz[m]**2)/terms.responsibilities[m].sum())),mean_residual_hz=float(np.sum(terms.responsibilities[m]*terms.residual_hz[m])/terms.responsibilities[m].sum()),position_gradient=np.einsum('nk,nki->i',terms.prediction_gradient[m],spatial[m]).tolist()) for k,m in groups.items()},satellites=[dict(number=int(n),mass=float(terms.responsibilities[:,j].sum()),relative_s=float((obj.basis@v[8:])[j]),gradient=np.einsum('n,ni->i',terms.prediction_gradient[:,j],spatial[:,j]).tolist()) for j,n in enumerate(obj.bank.numbers)])
        for label,mask in masks.items():
            sub=PositionObjective(subset(obs,mask),obj.bank,prior,obj.score,receiver_baseline_hz=obj.baseline[mask]);sub.design=obj.design[mask].copy()
            # Two seeds from the same arm only: sigma1 selected branch and other original branch.
            own=[r for r in finals if r['basin']==basin and r['arm']==arm];other=min(own,key=lambda r:r['fit']['objective'])
            for seedlabel,seed in [('sigma1-winner',v),('original-own-best',np.asarray(other['fit']['vector']))]:
                fit=fit_position(sub,seed,rf_arm=arm,maximum_seconds=12,maximum_iterations=300,local_center=np.asarray(old['basins'][basin]['center']),local_radius_km=old['basins'][basin]['radius_km']);row=candidate(sub,fit.vector,arm,basin,seedlabel,winner['calibration_penalty'],old['basins'][basin],fit);row['mask']=label;row['windows']=int(mask.sum());output['block_rows'].append(row);print(label,arm,seedlabel,row['objective'],row['stationarity'],flush=True);save()
    output['block_selected']={label:{arm:min((r for r in output['block_rows'] if r['mask']==label and r['arm']==arm and r['feasible']),key=lambda r:r['objective']) for arm in options.ARMS} for label in masks}
    for row in output['block_rows']:add_error(row)
    output['total_fit_elapsed_s']=sum(r['elapsed_s'] for r in output['rows']+output['block_rows']);output['status']='complete';save()

if __name__=='__main__':main()
