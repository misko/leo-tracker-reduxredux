"""Read-only saved-case reconstruction and matched cross-arm continuation."""
import csv
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SID = 'scan-fw-6bf407cfe8158445'

def shared_seeds(free, zero):
    """Both arms receive the identical union; zero projection happens at fit time."""
    return [('saved-free', np.array(free, float, copy=True)),
            ('saved-zero', np.array(zero, float, copy=True))]

def selection(rows):
    return min(rows, key=lambda r: r['selection_score'])

def arm_seed(vector, arm):
    result = np.array(vector, float, copy=True)
    if arm == 'zero-c':
        result[6] = 0.0
    return result

def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective, coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.analysis.regional_position_search import SpatialSearch, SpatialEvaluation, distinct_basins
    from leo.contracts.regional_position import RegionalPrior, PositionScore
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
    snapshot = json.loads((HERE.parent/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc = next(c['regional_document'] for c in snapshot['captures'] if c['session_id'] == SID)
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try: source = store.load(SID)
    finally: store.close()
    assert source.input_manifest_sha256 == doc['input_manifest_sha256']
    assert source.analysis_manifest_sha256 == doc['analysis_manifest_sha256']
    prepared = prepare_position_windows(source)
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    saved = doc['diagnostics']
    tle = next(s for s in archive.list_snapshots() if s.digest == saved['snapshot_sha256'] and s.collected_utc_ns == saved['snapshot_collected_utc_ns'])
    payload, _ = exclude_labelled_starlink_debris(archive.read(tle))
    catalogue = parse_element_sets(payload)
    indices = np.asarray([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')])
    prior = RegionalPrior(**doc['configuration']['prior'])
    bank, receipt = build_regional_bank(catalogue, indices, prepared.start_utc_ns, prepared.observations, prior, maximum_seconds=60)
    assert list(receipt.retained_numbers) == saved['bank']['retained_numbers']
    checkpoint = RegionalCheckpointStore(Path('/srv/bulk/leo'), SID, saved['checkpoint_binding'])
    prefix = canonical_digest(doc['configuration']['run'])
    basins = {}
    for method in doc['methods']:
        search = SpatialSearch(tuple(SpatialEvaluation(p['east_km'],p['north_km'],p['spacing_km'],p['objective']) for p in method['points'] if p['objective'] is not None),method['deferred_cells'],method['search_stop_reason'])
        for p in distinct_basins(search,count=3):
            key=f'point:{p.east_km:g}:{p.north_km:g}'
            basins[key]=max(basins.get(key,0),p.spacing_km)
    finals = [r for r in saved['final_starts'] if r['method']=='V16' and r['fit']]
    rows=[]
    for basin, spacing in sorted(basins.items()):
        cal=checkpoint.get(prefix+':'+basin+':calibration')['result']
        assoc=checkpoint.get(prefix+':'+basin+':association')['result']
        obj=PositionObjective(prepared.observations,bank.select(assoc['selected_indices']),prior,PositionScore(**doc['configuration']['scores']['V16']),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
        local_center=np.asarray(assoc['initial_vector'])[:2]
        arm_best={arm:min((r for r in finals if r['basin']==basin and r['arm']==arm),key=lambda r:r['fit']['objective']) for arm in ('fitted-c','zero-c')}
        penalty=arm_best['fitted-c']['calibration_penalty']
        for arm,r in arm_best.items():
            vector=np.asarray(r['fit']['vector']); value,_,_=obj.evaluate(vector)
            assert abs(value-r['fit']['objective'])<1e-6
            rows.append(dict(basin=basin,arm=arm,start='saved-incumbent',selection_score=value+penalty,objective=value,vector=vector.tolist(),elapsed_s=0,stop_reason=r['fit']['stop_reason'],stationarity=r['fit']['stationarity'],posterior_rms_hz=r['fit']['posterior_rms_hz']))
        for label,vector in shared_seeds(arm_best['fitted-c']['fit']['vector'],arm_best['zero-c']['fit']['vector']):
            for arm in ('fitted-c','zero-c'):
                fit=fit_position(obj,arm_seed(vector,arm),rf_arm=arm,maximum_seconds=10,maximum_iterations=300,local_center=local_center,local_radius_km=max(12.5,spacing/np.sqrt(2)))
                rows.append(dict(basin=basin,arm=arm,start=label,selection_score=fit.objective+penalty,objective=fit.objective,vector=fit.vector.tolist(),elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason,stationarity=fit.stationarity,posterior_rms_hz=fit.posterior_rms_hz))
                print(basin,arm,label,round(fit.objective+penalty,3),flush=True)
        # Include zero incumbent explicitly as a feasible free-c candidate.
        r=next(r for r in rows if r['basin']==basin and r['arm']=='zero-c' and r['start']=='saved-incumbent')
        rows.append({**r,'arm':'fitted-c','start':'zero-incumbent-envelope','stationarity':None,'stop_reason':'feasible-only-transfer'})
    # Evaluation only after score-only selections are final.
    selected={arm:selection([r for r in rows if r['arm']==arm]) for arm in ('fitted-c','zero-c')}
    selected['fitted-c-direct'] = selection([r for r in rows if r['arm']=='fitted-c' and r['start']!='zero-incumbent-envelope'])
    zero_best = selected['zero-c']
    if zero_best['selection_score'] < selected['fitted-c']['selection_score']:
        selected['fitted-c-final-envelope']={**zero_best,'arm':'fitted-c','start':'completed-zero-feasible-envelope','stationarity':None,'stop_reason':'feasible-only-transfer'}
    else:
        selected['fitted-c-final-envelope']=selected['fitted-c']
    for r in rows:
        lat,lon=coordinates(prior,r['vector'][:2]); lat0,lon0=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]); a,b=np.radians([lat,lon]); h=np.sin((a-lat0)/2)**2+np.cos(a)*np.cos(lat0)*np.sin((b-lon0)/2)**2
        r['horizontal_error_m']=float(6371008.8*2*np.arctan2(np.sqrt(h),np.sqrt(1-h)))
    output=dict(session_id=SID,snapshot_sha256=tle.digest,windows=len(prepared.observations.window_ids),budget=dict(seconds_per_fit=10,iterations=300,shared_starts=2),selected=selected,rows=rows)
    (HERE/'results.json').write_text(json.dumps(output,indent=2))
    with (HERE/'results.csv').open('w') as f:
        fields=[k for k in rows[0] if k!='vector']; writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps(selected,indent=2),flush=True)

if __name__=='__main__': main()
