"""Read-only server-oracle export for a particular acquisition and TLE snapshot.

Run in the frozen maintained-server Python environment. This tool is evaluation
infrastructure, never an ARM runtime dependency. No server memberships are put
in the response-free authority fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import numpy as np
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.sky.propagation import parse_element_sets
from leo.sky.frames import geodetic_to_ecef_km
from leo.contracts.digests import canonical_digest


def pack(path, states, ids, sites, tracks):
    with path.open('wb') as out:
        out.write(struct.pack('<5I2d',0x31434f4c,len(ids),states.shape[1],len(tracks),len(sites),-60.,10.))
        for site in sites:
            out.write(np.asarray(site['receiver']+site['up'],dtype='<f8').tobytes())
        for tr in tracks:
            t=np.asarray(tr['times_s'],dtype='<f8')
            out.write(struct.pack('<2I',len(t),len(np.unique(np.floor(t)))))
            out.write(t.tobytes())
            out.write(np.asarray(tr['measured_hz'],dtype='<f8').tobytes())
            out.write(np.asarray(tr['training_mask'],dtype='u1').tobytes())
        out.write(np.asarray(ids,dtype='<i4').tobytes())
        out.write(np.asarray(states,dtype='<f8').tobytes())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',required=True)
    parser.add_argument('--capture-manifest',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    started=time.monotonic()
    capture=json.loads(args.capture_manifest.read_text())
    status=AdaptiveTlePositionStoreV2(Path('/srv/bulk/leo')).status(args.session)
    if status.state!='complete':raise ValueError('server position reference is not complete')
    doc=status.manifest.document
    if doc.input_manifest_sha256!=canonical_digest(capture):raise ValueError('capture identity mismatch')
    origin=capture['timing']['first_sample_estimate_utc_ns']
    reader=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=next(s for s in reader.list_snapshots() if s.digest==doc.diagnostics['snapshot_digest'])
    payload=reader.read(snap)
    catalogue=parse_element_sets(exclude_labelled_starlink_debris(payload)[0])
    indices=np.array([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')])
    # Freeze the same response-independent validity screen as the server oracle.
    valid_parts=[]
    for begin in range(0,len(indices),256):
        _,_,valid=propagate_candidate_states(catalogue,indices[begin:begin+256],origin,
                                           np.arange(-507.,809.),np.array([0.]))
        valid_parts.extend(valid)
    valid=np.asarray(valid_parts,dtype=int)
    p,v,actual=propagate_candidate_states(catalogue,valid,origin,np.arange(-60.,361.,10.),np.array([0.]))
    if not np.array_equal(actual,valid):raise ValueError('orbit validity changed')
    states=np.concatenate((p[:,0],v[:,0]),axis=-1)
    ids=[int(catalogue.satellite_numbers[i]) for i in valid]
    sites=[]
    for prior in doc.priors:
        lat,lon=prior.selected.latitude_deg,prior.selected.longitude_deg
        latitude,longitude=np.deg2rad([lat,lon])
        sites.append({'name':prior.name,'latitude_deg':lat,'longitude_deg':lon,
            'receiver':geodetic_to_ecef_km(lat,lon,0).tolist(),
            'up':[float(np.cos(latitude)*np.cos(longitude)),float(np.cos(latitude)*np.sin(longitude)),float(np.sin(latitude))],
            'role':'published-selected-point-for-comparison-only',
            'search_region':prior.region.model_dump(mode='json')})
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'snapshot.tle').write_text(payload)
    (args.output/'server-reference.json').write_text(json.dumps(doc.model_dump(mode='json'),indent=2)+'\n')
    tracks=doc.diagnostics['track_evidence']
    pack(args.output/'authority.loc1',states,ids,sites,[])
    pack(args.output/'published-reference.loc1',states,ids,sites,tracks)
    np.save(args.output/'states.npy',states)
    meta={'schema':'leo-native-location-authority/v1','session_id':args.session,
          'capture_digest':doc.input_manifest_sha256,'start_utc_ns':origin,
          'tle_digest':snap.digest,'satellite_ids':ids,'knot_start_s':-60.,'knot_step_s':10.,
          'knot_count':states.shape[1],'sites':sites,'reference_track_count':len(tracks),
          'warning':'Published memberships are evaluation-only. Authority fixture contains zero tracks.',
          'server_prediction_bank':doc.diagnostics['prediction_bank'],
          'export_wall_s':time.monotonic()-started}
    meta['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir() if p.is_file()}
    (args.output/'authority.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps({'satellites':len(ids),'tracks':len(tracks),'seconds':meta['export_wall_s']}))


if __name__=='__main__':main()
