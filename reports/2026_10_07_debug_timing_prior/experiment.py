"""Read-only frozen timing-prior experiment; matched RF-arm starts and budgets."""
import json
from pathlib import Path
from dataclasses import replace, asdict
import numpy as np
from leo.application.regional_position_inputs import prepare_position_windows
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior, POSITION_SCORES
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import PositionObjective, coordinates
from leo.analysis.regional_position_fit import fit_position

HERE=Path(__file__).resolve().parent
SID='scan-fw-0695481606e1a3e8'

def penalty(vector, sigma, common=3.):
    return float(.5*(vector[7]/common)**2+.5*np.sum((vector[8:]/sigma)**2))

def serialize(value):
    if isinstance(value,np.ndarray): return value.tolist()
    if isinstance(value,np.generic): return value.item()
    raise TypeError(type(value).__name__)

def main():
    snapshot=json.loads((HERE.parent/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(x for x in snapshot['captures'] if x['session_id']==SID)['regional_document']
    root=Path('/srv/bulk/leo'); store=ScannerTrackingInputStore(root)
    try: source=store.load(SID)
    finally: store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256']
    assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prepared=prepare_position_windows(source); obs=prepared.observations; prior=RegionalPrior()
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=next(x for x in archive.list_snapshots() if x.digest==doc['diagnostics']['snapshot_sha256'] and x.collected_utc_ns==doc['diagnostics']['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(snap)); catalogue=parse_element_sets(payload)
    indices=np.array([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')])
    bank,receipt=build_regional_bank(catalogue,indices,prepared.start_utc_ns,obs,prior,maximum_seconds=100)
    checkpoint=RegionalCheckpointStore(root,SID,doc['diagnostics']['checkpoint_binding'])
    prefix=canonical_digest(doc['configuration']['run'])+':'
    finals=[r for r in doc['diagnostics']['final_starts'] if r['fit']]
    outputs={'session_id':SID,'bank':asdict(receipt),'repriced':[],'fits':[],'observations':len(obs.window_ids),'timing_offsets':[]}
    for basin in ('point:-56.25:-68.75','point:-93.75:-81.25'):
        calibration=checkpoint.get(prefix+basin+':calibration')['result']
        association=checkpoint.get(prefix+basin+':association')['result']
        subset=bank.select(association['selected_indices'])
        baseline=np.asarray(calibration['receiver_baseline_hz'])
        rows=[r for r in finals if r['basin']==basin]
        calpen=rows[0]['calibration_penalty']
        center=np.asarray(association['initial_vector'][:2])
        for sigma in (.15,.5,1.):
            objective=PositionObjective(obs,subset,prior,replace(POSITION_SCORES['V16'],relative_sigma_s=sigma),receiver_baseline_hz=baseline)
            for r in rows:
                v=np.asarray(r['fit']['vector']); val,_,terms=objective.evaluate(v)
                outputs['repriced'].append(dict(basin=basin,method=r['method'],arm=r['arm'],start=r['start'],sigma=sigma,objective=val,total=val+calpen,data_nll=terms.nll,penalty=penalty(v,sigma)))
                if sigma==.15 and r['method']=='V16' and r['arm']=='fitted-c':
                    relative=objective.basis@v[8:]
                    outputs['timing_offsets'].append(dict(basin=basin,start=r['start'],common_s=v[7],numbers=subset.numbers,relative_s=relative,absolute_s=relative+v[7]))
            # Same pool and ranking for both arms; no reference location in selection.
            pool=[np.asarray(r['fit']['vector']) for r in rows]
            pool.append(np.asarray(association['initial_vector']))
            def rank(v):
                z=v.copy(); z[6]=0
                return objective.evaluate(v)[0]+objective.evaluate(z)[0]
            starts=sorted(pool,key=rank)[:2]
            for arm in ('zero-c','fitted-c'):
                for i,start in enumerate(starts):
                    fit=fit_position(objective,start,rf_arm=arm,maximum_seconds=8,maximum_iterations=300,local_center=center,local_radius_km=12.5)
                    value,_,terms=objective.evaluate(fit.vector)
                    lat,lon=coordinates(prior,fit.vector[:2])
                    # Great-circle reference error only for evaluation, never selection.
                    la,lo,ra,ro=np.deg2rad([lat,lon,doc['reference_latitude_deg'],doc['reference_longitude_deg']])
                    hav=np.sin((la-ra)/2)**2+np.cos(la)*np.cos(ra)*np.sin((lo-ro)/2)**2
                    error=2*6371008.8*np.arcsin(np.sqrt(np.clip(hav,0,1)))
                    block=np.floor((obs.times_s-obs.times_s.min())/60).astype(int)
                    support=terms.responsibilities.sum(axis=1)
                    residual_weight=(terms.responsibilities*terms.residual_hz**2).sum(axis=1)
                    blocks=[dict(block=int(b),count=int(np.sum(block==b)),signal_mass=float(support[block==b].sum()),weighted_rms_hz=float(np.sqrt(residual_weight[block==b].sum()/max(support[block==b].sum(),1e-12)))) for b in np.unique(block)]
                    outputs['fits'].append(dict(basin=basin,sigma=sigma,arm=arm,start=i,start_vector=start.copy(),fit=asdict(fit),total=value+calpen,data_nll=terms.nll,error_m=float(error),blocks=blocks))
                    (HERE/'results.json').write_text(json.dumps(outputs,default=serialize,indent=2))
                    print(basin,sigma,arm,i,round(value+calpen,2),round(error,1),fit.stop_reason,flush=True)
    (HERE/'results.json').write_text(json.dumps(outputs,default=serialize,indent=2))

if __name__=='__main__': main()
