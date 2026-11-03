"""Read-only frozen-bank continuation, no production writer ports used."""
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
import numpy as np
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_score import PositionObjective, coordinates
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import POSITION_SCORES, RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

OUT = Path(__file__).resolve().parent
SID = 'scan-fw-e3bebc228093a125'

def distance_m(lat, lon, reference):
    a,b,c,d=np.radians([lat,lon,*reference])
    h=np.sin((c-a)/2)**2+np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2
    return float(6371008.8*2*np.arcsin(np.sqrt(h)))

def plain(value):
    if isinstance(value,np.ndarray): return value.tolist()
    if isinstance(value,np.generic): return value.item()
    raise TypeError(type(value).__name__)

def main():
    snapshot=json.loads((OUT.parent/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(r['regional_document'] for r in snapshot['captures'] if r['session_id']==SID)
    diag=doc['diagnostics']; root=Path('/srv/bulk/leo')
    store=ScannerTrackingInputStore(root)
    try: source=store.load(SID)
    finally: store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256']
    assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prepared=prepare_position_windows(source)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    ref=next(r for r in archive.list_snapshots() if r.digest==diag['snapshot_sha256'] and r.collected_utc_ns==diag['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(ref))
    cat=parse_element_sets(payload)
    indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')])
    prior=RegionalPrior()
    bank,receipt=build_regional_bank(cat,indices,prepared.start_utc_ns,prepared.observations,prior,maximum_seconds=60)
    checkpoints=RegionalCheckpointStore(root,SID,diag['checkpoint_binding'])
    prefix=canonical_digest(doc['configuration']['run'])
    results=[]
    for method,basin in [('T1AT','point:-106.25:-81.25'),('V16','point:-68.75:-106.25')]:
        calibration=checkpoints.get(prefix+':'+basin+':calibration')['result']
        association=checkpoints.get(prefix+':'+basin+':association')['result']
        subset=bank.select(association['selected_indices'])
        objective=PositionObjective(prepared.observations,subset,prior,POSITION_SCORES[method],receiver_baseline_hz=np.asarray(calibration['receiver_baseline_hz']))
        center=np.asarray(association['initial_vector'])[:2]
        saved=next(f for f in diag['final_starts'] if f['method']==method and f['basin']==basin and f['arm']=='fitted-c' and f['start']=='associated')
        start=np.asarray(saved['fit']['vector'])
        repriced=objective.evaluate(start)[0]
        assert abs(repriced-saved['fit']['objective'])<1e-6, (repriced,saved['fit']['objective'])
        east,north=map(float,basin.split(':')[1:])
        grid_levels=[level for level in doc['configuration']['run']['levels_km'] if all(abs((v+500)/level-.5-round((v+500)/level-.5))<1e-8 for v in (east,north))]
        assert grid_levels==[12.5], grid_levels
        if '--audit-only' in sys.argv:
            print(json.dumps({'method':method,'saved_objective':saved['fit']['objective'],'repriced_objective':repriced,'grid_levels_km':grid_levels,'selected_satellites':len(subset.numbers),'original_local_radius_km':max(12.5,grid_levels[0]/np.sqrt(2))}),flush=True)
            continue
        for radius in (12.5,25.0):
            for arm in ('fitted-c','zero-c'):
                fit=fit_position(objective,start.copy(),rf_arm=arm,maximum_seconds=35,maximum_iterations=600,local_center=center,local_radius_km=radius)
                lat,lon=coordinates(prior,fit.vector[:2])
                row={'method':method,'basin':basin,'arm':arm,'radius_km':radius,'local_center':center.tolist(),'distance_from_local_center_km':float(np.linalg.norm(fit.vector[:2]-center)),'latitude_deg':lat,'longitude_deg':lon,'horizontal_error_m':distance_m(lat,lon,(doc['reference_latitude_deg'],doc['reference_longitude_deg'])),'saved_fitted_objective':saved['fit']['objective'],**asdict(fit)}
                results.append(row)
                (OUT/'results.json').write_text(json.dumps({'session_id':SID,'snapshot_sha256':ref.digest,'windows':len(prepared.observations.window_ids),'bank_receipt':asdict(receipt),'matched_start':'saved fitted-c associated vector; c reset only in zero-c','maximum_seconds':35,'maximum_iterations':600,'results':results},default=plain,indent=2))
                print(method,arm,radius,fit.objective,fit.stationarity,row['horizontal_error_m'],flush=True)
    if '--audit-only' in sys.argv: return
    with (OUT/'results.csv').open('w') as handle:
        keys=['method','arm','radius_km','objective','stationarity','converged','boundary','stop_reason','elapsed_s','horizontal_error_m','distance_from_local_center_km']
        writer=csv.DictWriter(handle,keys,extrasaction='ignore');writer.writeheader();writer.writerows(results)

if __name__=='__main__': main()
