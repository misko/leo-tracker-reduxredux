"""Read-only, reference-conditioned nuisance diagnostic; no location search."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_26_joint_location_prototype'))
from run_prototype import point_factory
from nuisance_core import fit_profiles, select_fit
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import build_prediction_banks, RegionalTrackPredictionEvaluator


def main():
    old=json.loads((HERE/'results.json').read_text())
    root=Path('/srv/bulk/leo')
    manifest=AdaptiveTlePositionStoreV2(root).status(old['session_id']).manifest
    assert manifest.document_sha256==old['document_sha256']
    doc=manifest.document.model_dump(mode='json')
    store=ScannerTrackingInputStore(root)
    try:
        prepared=prepare_adaptive_tle_position_inputs(old['session_id'],inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally: store.close()
    assert prepared.evidence_sha256==old['evidence_sha256']
    assert prepared.snapshot_digest==old['snapshot_digest']
    tracks={r['track_id']:r for r in old['tracks']}
    ids={r['reno']['candidate_id'] for r in old['tracks']}|{r['reference_top3'][0]['id'] for r in old['tracks']}
    indices=[i for i in prepared.candidate_indices if str(prepared.catalogue.satellite_numbers[i]) in ids]
    taus=np.arange(-30.,31.)
    banks,receipt=build_prediction_banks(prepared.catalogue,indices,prepared.start_utc_ns,prepared.tracks,taus_s=taus)
    sites={'reference':doc['diagnostics']['reference_evaluation_only'], 'reno':next(p['selected'] for p in doc['priors'] if p['name']=='reno')}
    output={'session_id':old['session_id'],'document_sha256':old['document_sha256'],'evidence_sha256':prepared.evidence_sha256,
            'snapshot_digest':prepared.snapshot_digest,'protocol':{'locations_and_identities_frozen':True,'base_tau_seconds':[-5,5,1],'expanded_tau_seconds':[-30,30,1],
            'linear_drift':'training-only slope of measured-minus-Doppler residual at selected tau; no tau/identity refit for drift model',
            'selection':'tau and constant offset fit on training; identities inherited from prior evaluation-selected diagnostic',
            'scope':'one selected failure, 46 correlated paired tracks; not generalization or independent satellite truth',
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'core_sha256':hashlib.sha256((HERE/'nuisance_core.py').read_bytes()).hexdigest()},'branches':{}}
    for label,site in sites.items():
        rows={}
        evaluator=RegionalTrackPredictionEvaluator(banks,point_factory(site['latitude_deg'],site['longitude_deg']),taus_s=taus)
        for b in evaluator(0,0):
            orig=tracks[b.track_id]
            expected=orig['reference_top3'][0] if label=='reference' else orig['reno']
            ident=expected['id'] if label=='reference' else expected['candidate_id']
            found=np.flatnonzero(np.asarray(b.candidate_ids).astype(str)==ident)
            if not len(found): continue
            index=int(found[0])
            assert bool(np.asarray(b.visible)[index])
            profile,centered=fit_profiles(b.times_s,b.measured_hz,b.predictions_hz[index],b.training_mask,taus)
            base=select_fit(profile,centered,b.times_s,b.training_mask,5)
            wide=select_fit(profile,centered,b.times_s,b.training_mask,30)
            expected_score=expected['score_hz'] if label=='reference' else expected['heldout_rms_hz']
            expected_offset=expected['offset_hz'] if label=='reference' else expected['frequency_offset_hz']
            assert base['tau_s']==expected['tau_s']
            assert abs(base['score_rms_hz']-expected_score)<1e-6
            assert abs(base['offset_hz']-expected_offset)<1e-6
            rows[b.track_id]={'track_id':b.track_id,'satellite_id':ident,'span_s':orig['span_s'],'weight_s':orig['occupied_seconds'],
                'base':base,'expanded':wide,'profile':profile,'base_score_parity_hz':base['score_rms_hz']-expected_score}
        assert set(rows)==set(tracks)
        output['branches'][label]=[rows[r['track_id']] for r in old['tracks']]
    print(json.dumps(output,indent=2))


if __name__=='__main__': main()
