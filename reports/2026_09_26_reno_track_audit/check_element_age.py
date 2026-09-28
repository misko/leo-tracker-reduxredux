"""Compare older causal element sets at fixed reference geometry and identity."""
import json
from pathlib import Path
import numpy as np
from compare_scan_clock import AdaptiveTlePositionStoreV2,TleArchiveReader,build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory
from leo.analysis.adaptive_tle_prediction import AdaptiveTrackInput
from leo.sky.propagation import parse_element_sets
from nuisance_core import fit_profiles,select_fit

HERE=Path(__file__).resolve().parent
d=json.loads((HERE/'deep_diagnosis.json').read_text())
doc=AdaptiveTlePositionStoreV2(Path('/srv/bulk/leo')).status(d['session_id']).manifest.document.model_dump(mode='json')
assert doc['evidence_sha256']==d['evidence_sha256']
evidence={r['track_id']:r for r in doc['diagnostics']['track_evidence']}
archive=TleArchiveReader(Path('/var/lib/leo/tle'));start=d['start_utc_ns'];out=[]
site=doc['diagnostics']['reference_evaluation_only'];taus=np.round(np.arange(-300,301)/10,1)
for sat,prefixes,ages in [(63850,('ad00e08d','d4446f2d'),(0,48)),(61518,('46b5f08c',),(0,6))]:
    tracks=[]
    for tid,e in evidence.items():
        if tid[7:15] in prefixes: tracks.append(AdaptiveTrackInput(tid,tuple(e['observation_ids']),np.array(e['times_s']),np.array(e['measured_hz']),np.array(e['training_mask'],bool)))
    for hours in ages:
        snapshot=archive.select_latest_before(start-int(max(505,hours*3600)*1e9),provider='space-track')
        cat=parse_element_sets(archive.read(snapshot));i=cat.satellite_numbers.index(sat)
        banks,_=build_prediction_banks(cat,[i],start,tracks,taus_s=taus)
        for b in RegionalTrackPredictionEvaluator(banks,point_factory(site['latitude_deg'],site['longitude_deg']),taus_s=taus)(0,0):
            assert len(b.candidate_ids)==1 and b.visible[0]
            p,r=fit_profiles(b.times_s,b.measured_hz,b.predictions_hz[0],b.training_mask,taus)
            out.append({'satellite_id':sat,'track_id':b.track_id,'snapshot_digest':snapshot.digest,
                        'snapshot_age_hours':(start-snapshot.collected_utc_ns)/3.6e12,
                        'element_age_hours':(start-cat.element_epoch_utc_ns()[i])/3.6e12,
                        'fit':select_fit(p,r,b.times_s,b.training_mask,30)})
print(json.dumps({'scope':'fixed identities and location, causal snapshots only; no independent truth or geographic search','rows':out},indent=2))
