"""Trace original deployed fitting from original association starts, read-only."""
import hashlib
import inspect
import json
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize as scipy_minimize
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.regional_position_inputs import prepare_position_windows
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import PositionObjective, coordinates
import leo.analysis.regional_position_fit as fitting
from leo.contracts.regional_position import RegionalPrior, PositionScore
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SID='scan-fw-6bf407cfe8158445'
BASIN='point:-87.5:-87.5'

def setup():
    snapshot=json.loads((ROOT/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(c['regional_document'] for c in snapshot['captures'] if c['session_id']==SID)
    for relative,digest in doc['configuration']['source_digests'].items():
        path=Path(fitting.__file__).parents[1]/relative
        assert 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()==digest
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try: source=store.load(SID)
    finally: store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256']
    assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prepared=prepare_position_windows(source)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));saved=doc['diagnostics']
    tle=next(s for s in archive.list_snapshots() if s.digest==saved['snapshot_sha256'] and s.collected_utc_ns==saved['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(tle));catalogue=parse_element_sets(payload)
    indices=np.asarray([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')])
    prior=RegionalPrior(**doc['configuration']['prior'])
    bank,receipt=build_regional_bank(catalogue,indices,prepared.start_utc_ns,prepared.observations,prior,maximum_seconds=60)
    assert list(receipt.retained_numbers)==saved['bank']['retained_numbers']
    cp=RegionalCheckpointStore(Path('/srv/bulk/leo'),SID,saved['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])+':'+BASIN
    cal=cp.get(prefix+':calibration')['result'];assoc=cp.get(prefix+':association')['result']
    objective=PositionObjective(prepared.observations,bank.select(assoc['selected_indices']),prior,PositionScore(**doc['configuration']['scores']['V16']),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
    for row in saved['final_starts']:
        if row['basin']==BASIN and row['method']=='V16' and row['fit']:
            assert abs(objective.evaluate(row['fit']['vector'])[0]-row['fit']['objective'])<1e-6
    return doc,objective,np.asarray(assoc['initial_vector'],float)

def run(doc,objective,initial,start_name,arm,fit_function=fitting.fit_position,label='original'):
    begun=time.monotonic();events=[];iterations=[]
    class Recording:
        def __getattr__(self,key):return getattr(objective,key)
        def evaluate(self,vector):
            value,gradient,terms=objective.evaluate(vector)
            events.append(dict(evaluation=len(events),elapsed_s=time.monotonic()-begun,value=value,vector=vector.tolist(),gradient=gradient.tolist(),signal_mass=float(terms.responsibilities.sum()),clutter_over_99=int(np.sum(terms.clutter_probability>.99)),top_satellite=np.argmax(terms.responsibilities,axis=1).tolist(),responsibility_max_mean=float(np.max(terms.responsibilities,axis=1).mean())))
            return value,gradient,terms
    def minimize(fun,x0,**kwargs):
        def callback(z):
            # Callback is after iteration's objective evaluation, so record query
            # inventory boundaries without introducing extra optimizer evaluations.
            iterations.append(dict(iteration=len(iterations)+1,evaluations=len(events),z=z.tolist()))
        return scipy_minimize(fun,x0,callback=callback,**kwargs)
    fitting.minimize=minimize
    fit_function.__globals__['minimize']=minimize
    start=initial.copy()
    if start_name=='zero-timing':start[7:]=0
    result=fit_function(Recording(),start,rf_arm=arm,maximum_seconds=20,maximum_iterations=300,local_center=initial[:2],local_radius_km=25/np.sqrt(2))
    lat,lon=coordinates(objective.prior,result.vector[:2]);lat0,lon0=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);a,b=np.radians([lat,lon]);h=np.sin((a-lat0)/2)**2+np.cos(a)*np.cos(lat0)*np.sin((b-lon0)/2)**2
    receipt=dict(label=label,start=start_name,arm=arm,objective=result.objective,error_m=float(6371008.8*2*np.arctan2(np.sqrt(h),np.sqrt(1-h))),stationarity=result.stationarity,stop_reason=result.stop_reason,elapsed_s=result.elapsed_s,vector=result.vector.tolist(),events=events,iterations=iterations)
    (HERE/f'{label}_{start_name}_{arm}.json').write_text(json.dumps(receipt))
    print(label,start_name,arm,result.objective,receipt['error_m'],result.stop_reason,len(events),flush=True)
    return receipt

def main():
    doc,obj,initial=setup();results=[]
    for start in ('associated','zero-timing'):
        for arm in ('fitted-c','zero-c'):results.append(run(doc,obj,initial,start,arm))
    (HERE/'summary.json').write_text(json.dumps([{k:v for k,v in r.items() if k not in ('events','iterations')} for r in results],indent=2))

def targeted():
    doc,obj,initial=setup();results=[]
    source=inspect.getsource(fitting.fit_position)
    original='scales = np.r_[1.0, 1.0, 200.0, 2.0, 200.0, 2.0, 200.0, np.ones(objective.size - 7)]'
    assert original in source
    for label,replacement in [('cscale20','scales = np.r_[1.0, 1.0, 200.0, 2.0, 200.0, 2.0, 20.0, np.ones(objective.size - 7)]'),('allscale01',original+' * 0.1')]:
        namespace=dict(fitting.__dict__);exec(source.replace(original,replacement),namespace)
        for arm in ('fitted-c','zero-c'):results.append(run(doc,obj,initial,'associated',arm,namespace['fit_position'],label))
    (HERE/'targeted_summary.json').write_text(json.dumps([{k:v for k,v in r.items() if k not in ('events','iterations')} for r in results],indent=2))

if __name__=='__main__':
    import sys
    targeted() if '--targeted' in sys.argv else main()
