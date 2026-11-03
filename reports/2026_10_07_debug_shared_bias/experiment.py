"""Conditional deletion diagnostics; no input/store/checkpoint writes."""
import json
from dataclasses import fields
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SID = 'scan-fw-6a376b600fc2f542'

def subset(obs, mask):
    from leo.contracts.regional_position import PositionObservations
    return PositionObservations(**{f.name: tuple(np.asarray(obs.window_ids)[mask]) if f.name == 'window_ids' else getattr(obs, f.name)[mask] for f in fields(obs)})

def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective, coordinates, predict_orbits
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import RegionalPrior, PositionScore
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
    snapshot=json.loads((HERE.parent/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(c['regional_document'] for c in snapshot['captures'] if c['session_id']==SID)
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try: source=store.load(SID)
    finally: store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256']
    assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prepared=prepare_position_windows(source); obs=prepared.observations; saved=doc['diagnostics']
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    tle=next(s for s in archive.list_snapshots() if s.digest==saved['snapshot_sha256'] and s.collected_utc_ns==saved['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(tle)); catalogue=parse_element_sets(payload)
    indices=np.asarray([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')])
    prior=RegionalPrior(**doc['configuration']['prior'])
    bank,receipt=build_regional_bank(catalogue,indices,prepared.start_utc_ns,obs,prior,maximum_seconds=60)
    assert list(receipt.retained_numbers)==saved['bank']['retained_numbers']
    checkpoint=RegionalCheckpointStore(Path('/srv/bulk/leo'),SID,saved['checkpoint_binding'])
    prefix=canonical_digest(doc['configuration']['run'])+':point:-93.75:-81.25'
    cal=checkpoint.get(prefix+':calibration')['result']; assoc=checkpoint.get(prefix+':association')['result']
    bank=bank.select(assoc['selected_indices'])
    obj=PositionObjective(obs,bank,prior,PositionScore(**doc['configuration']['scores']['T1AT']),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
    incumbents={arm:min((r for r in saved['final_starts'] if r['method']=='T1AT' and r['arm']==arm and r['basin']=='point:-93.75:-81.25' and r['fit']),key=lambda r:r['fit']['objective']) for arm in ('fitted-c','zero-c')}
    for arm,r in incumbents.items(): assert abs(obj.evaluate(np.asarray(r['fit']['vector']))[0]-r['fit']['objective'])<1e-6
    vector=np.asarray(incumbents['fitted-c']['fit']['vector']); _,gradient,terms=obj.evaluate(vector)
    resp=terms.responsibilities; mass=resp.sum(axis=1); residual=(resp*terms.residual_hz).sum(axis=1)/np.maximum(mass,1e-30)
    prediction,visible,spatial,timing=predict_orbits(bank,obs,prior,vector[:2],vector[7]+obj.basis@vector[8:])
    spatial_grad=np.einsum('nk,nki->ni',terms.prediction_gradient,spatial)
    blocks={}; masks={'all':np.ones(len(mass),bool)}
    for rx in np.unique(obs.receiver): masks[f'keep-rx-{rx}']=obs.receiver==rx
    midpoint=(obs.times_s.min()+obs.times_s.max())/2
    masks['early-half']=obs.times_s<=midpoint; masks['late-half']=obs.times_s>midpoint
    diagnostic_groups={**{f'rx-{r}':obs.receiver==r for r in np.unique(obs.receiver)},**{f'channel-{c}':obs.channel==c for c in np.unique(obs.channel)},'early-half':masks['early-half'],'late-half':masks['late-half']}
    for label,mask in diagnostic_groups.items():
        blocks[label]=dict(windows=int(mask.sum()),signal_mass=float(mass[mask].sum()),mean_residual_hz=float(np.sum(mass[mask]*residual[mask])/mass[mask].sum()),rms_hz=float(np.sqrt(np.sum(resp[mask]*terms.residual_hz[mask]**2)/resp[mask].sum())),position_gradient=spatial_grad[mask].sum(axis=0).tolist())
    satellites=[dict(number=int(number),signal_mass=float(resp[:,j].sum()),mean_residual_hz=float(np.sum(resp[:,j]*terms.residual_hz[:,j])/max(resp[:,j].sum(),1e-30)),position_gradient=np.einsum('n,ni->i',terms.prediction_gradient[:,j],spatial[:,j]).tolist()) for j,number in enumerate(bank.numbers)]
    rows=[]
    for label,mask in masks.items():
        sub=PositionObjective(subset(obs,mask),bank,prior,obj.score,receiver_baseline_hz=obj.baseline[mask]); sub.design=obj.design[mask].copy()
        for seed_arm in ('fitted-c','zero-c'):
            for arm in ('fitted-c','zero-c'):
                start=np.asarray(incumbents[seed_arm]['fit']['vector']).copy()
                if arm=='zero-c': start[6]=0
                fit=fit_position(sub,start,rf_arm=arm,maximum_seconds=12,maximum_iterations=300,local_center=np.asarray(assoc['initial_vector'])[:2],local_radius_km=12.5)
                lat,lon=coordinates(prior,fit.vector[:2]); a,b=np.radians([lat,lon]); a0,b0=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]); h=np.sin((a-a0)/2)**2+np.cos(a)*np.cos(a0)*np.sin((b-b0)/2)**2
                row=dict(mask=label,arm=arm,seed=seed_arm,windows=int(mask.sum()),objective=fit.objective,rms_hz=fit.posterior_rms_hz,error_m=float(6371008.8*2*np.arctan2(np.sqrt(h),np.sqrt(1-h))),vector=fit.vector.tolist(),stop_reason=fit.stop_reason,converged=fit.converged,stationarity=fit.stationarity,elapsed_s=fit.elapsed_s)
                rows.append(row);print(json.dumps(row),flush=True)
                (HERE/'results.json').write_text(json.dumps(dict(session_id=SID,verified_input_sha256=source.input_manifest_sha256,verified_analysis_sha256=source.analysis_manifest_sha256,tle_sha256=tle.digest,blocks=blocks,satellites=satellites,rows=rows),indent=2))

if __name__=='__main__': main()
