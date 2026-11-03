"""Freeze a real published DS9 all-track result and compact orbit tables."""
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.sky.propagation import parse_element_sets
from leo.cli.adaptive_tle_position import _coordinates
from leo.sky.frames import geodetic_to_ecef_km

HERE = Path(__file__).resolve().parent
SESSION = 'scan-fw-3cfdaa6d75762cad'


def main():
    started = time.monotonic()
    d = AdaptiveTlePositionStoreV2(Path('/srv/bulk/leo')).status(SESSION).manifest.document
    reader = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        source = reader.load(SESSION)
        start = source.timing.first_sample_estimate_utc_ns
        assert source.analysis_manifest_sha256 == d.analysis_manifest_sha256
    finally:
        reader.close()
    tracks = d.diagnostics['track_evidence']
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    snap = next(s for s in archive.list_snapshots() if s.digest == d.diagnostics['snapshot_digest'])
    payload = archive.read(snap)
    catalogue = parse_element_sets(exclude_labelled_starlink_debris(payload)[0])
    indices = np.array([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')])
    # Same full-window validity screen as the current server, not site-conditioned.
    coarse, _, valid = propagate_candidate_states(catalogue,indices,start,np.arange(-507.,809.),np.array([0.]))
    del coarse
    lo = np.floor(min(min(t['times_s']) for t in tracks)-5)
    hi = np.ceil(max(max(t['times_s']) for t in tracks)+5)
    points = []
    for prior in d.priors:
        lat,lon = prior.selected.latitude_deg,prior.selected.longitude_deg
        point = dict(name=prior.name,latitude_deg=lat,longitude_deg=lon,
                     receiver=geodetic_to_ecef_km(lat,lon,0).tolist(),
                     up=[np.cos(np.deg2rad(lat))*np.cos(np.deg2rad(lon)),np.cos(np.deg2rad(lat))*np.sin(np.deg2rad(lon)),np.sin(np.deg2rad(lat))],
                     expected_score_hz=prior.selected.capped_weighted_rmse_hz,
                     expected_tracks=d.diagnostics['selected_track_scores'][prior.name])
        points.append(point)
    # One-second common table supplies both the unchanged coarse visibility
    # interpolation and 10/30/60-second Hermite endpoints for experiments.
    base = float(np.floor(lo/60)*60)
    stop = float(np.ceil(hi/60)*60)
    knots = np.arange(base,stop+1)
    p,v,ids = propagate_candidate_states(catalogue,valid,start,knots,np.array([0.]))
    assert np.array_equal(ids,valid)
    states=np.concatenate((p[:,0],v[:,0]),axis=-1)
    local=HERE/'local';local.mkdir(exist_ok=True)
    np.save(local/'states.npy',states)
    meta=dict(session_id=SESSION,start_utc_ns=start,input_digest=d.input_manifest_sha256,
              analysis_digest=d.analysis_manifest_sha256,snapshot_digest=snap.digest,
              snapshot_payload_sha256=hashlib.sha256(payload.encode()).hexdigest(),
              catalogue_count=len(indices),valid_count=len(valid),satellite_ids=[int(catalogue.satellite_numbers[i]) for i in valid],
              knot_start_s=base,knot_step_s=1,knots=len(knots),tracks=tracks,points=points,
              original_prediction_bank=d.diagnostics['prediction_bank'],
              states_sha256=hashlib.sha256((local/'states.npy').read_bytes()).hexdigest(),
              export_seconds=time.monotonic()-started)
    (HERE/'inputs.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps({k:meta[k] for k in ['session_id','catalogue_count','valid_count','knots','export_seconds']})+' tracks='+str(len(tracks)),flush=True)


if __name__=='__main__':main()
