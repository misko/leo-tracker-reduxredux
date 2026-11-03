"""Verify capture-bound pose metadata and report nominal off-axis angles."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT.parent/'2026_10_02_multiscan_localization'),str(ROOT.parent/'2026_10_02_localization_benchmark')]


def digest(value):return 'sha256:'+hashlib.sha256(value).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def run():
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from all_visible_bank import load_expanded_scan
    from joint_inputs import _coordinates,_ecef
    receipt=json.loads((ROOT/'later-tle-timing-aligned-v2/receipt.json').read_text())
    catalogue=parse_element_sets(Path(receipt['latest_snapshot']['path']).read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    captures=[];angles=[]
    for scan in receipt['scans']:
        sid=scan['session']
        path=Path('/srv/bulk/leo/capture-pose/gauss-r20-lt3d-004b-20261001-v1')/(sid+'.json')
        raw=path.read_bytes();pose=json.loads(raw);authority=pose['pose_authority']
        manifest=json.loads((ROOT.parent/'2026_10_02_ds13_from_911c4e5d/local/published'/(sid+'.json')).read_text())
        capture=next(c for c in json.loads((ROOT.parent/'2026_10_02_ds13_from_911c4e5d/local/manifest.json').read_text())['captures'] if c['session_id']==sid)
        assert pose['binding_digest']==digest(canonical({k:v for k,v in pose.items() if k!='binding_digest'}))
        assert pose['pose_authority_digest']==digest(canonical(authority))
        assert pose['session_id']==sid and pose['manifest_sha256']==capture['manifest_sha256']
        assert pose['capture_start_earliest_utc_ns']==manifest['timing']['first_sample_earliest_utc_ns']
        assert pose['capture_end_utc_ns']==manifest['timing']['terminal_realtime_ns']
        assert authority['valid_from_utc_ns']<=pose['capture_start_earliest_utc_ns']<pose['capture_end_utc_ns']<authority['valid_until_utc_ns']
        data=load_expanded_scan(sid);p=np.array(scan['later_fit']['parameters']);fitlat,fitlon=_coordinates(p[:2])
        lat,lon=authority['latitude_deg'],authority['longitude_deg']
        site=_ecef(lat,lon);a,b=np.deg2rad([lat,lon])
        east=np.array([-np.sin(b),np.cos(b),0]);north=np.array([-np.sin(a)*np.cos(b),-np.sin(a)*np.sin(b),np.cos(a)])
        up=np.array([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
        for t in receipt['tracks']:
            if t['session']!=sid:continue
            number=t['catalog_number'];i=int(np.flatnonzero(data.numbers==number)[0]);ci=lookup[number]
            pos,vel,valid=propagate_candidate_states(catalogue,[ci],scan['origin_utc_ns'],np.array(t['time_s']),np.array([p[6+i]]))
            assert list(valid)==[ci]
            direction=pos[0,0]-site;direction/=np.linalg.norm(direction,axis=1)[:,None]
            azimuth=next(r['azimuth_deg'] for r in authority['receivers'] if r['receiver_id']==t['receiver'])
            az=np.deg2rad(azimuth);el=np.deg2rad(90-authority['nominal_outward_tilt_deg'])
            beam=np.cos(el)*np.sin(az)*east+np.cos(el)*np.cos(az)*north+np.sin(el)*up
            off=np.rad2deg(np.arccos(np.clip(direction@beam,-1,1)))
            east_component=direction@east
            azimuths=np.mod(np.rad2deg(np.arctan2(east_component,direction@north)),360)
            elevations=np.rad2deg(np.arcsin(direction@up))
            peers=[r for r in receipt['tracks'] if r['session']==sid and r['catalog_number']==number and r['receiver']!=t['receiver']]
            peer_times=np.concatenate([r['time_s'] for r in peers]) if peers else np.array([])
            # Final-track support only: not proof of nondetection in the other RX.
            simultaneous=np.array([bool(len(peer_times) and np.min(abs(peer_times-value))<=.15) for value in t['time_s']])
            wrong_side=(east_component>0) if t['receiver']==0 else (east_component<0)
            angles.append(dict(scan=scan['scan'],satellite=number,receiver=t['receiver'],
                duration_s=float(np.ptp(t['time_s'])),nominal_off_axis_min_median_max_deg=[float(off.min()),float(np.median(off)),float(off.max())],
                points=len(east_component),east_count=int(np.sum(east_component>0)),west_count=int(np.sum(east_component<0)),
                other_rx_has_final_track=bool(peers),other_rx_near_time_count=int(simultaneous.sum()),
                no_other_final_point_count=int((~simultaneous).sum()),opposite_side_without_other_final_point_count=int(np.sum(wrong_side&~simultaneous)),
                time_s=t['time_s'],azimuth_deg=azimuths.tolist(),elevation_deg=elevations.tolist(),
                east_component=east_component.tolist(),near_time_other_rx=simultaneous.tolist()))
        captures.append(dict(scan=scan['scan'],path=str(path),sha256=digest(raw),pose=pose,bindings_verified=True,
                             prior_fit_lat_lon=[float(fitlat),float(fitlon)]))
    output=ROOT/'prior-position-audit/pointing-evidence.json'
    output.write_text(json.dumps(dict(captures=captures,tracks=angles,
        scope='Capture bindings verified. Sky directions use capture-bound roof coordinates, which differ from prior fitted reference site. Angles assume a level mount and nominal 70-degree elevation, '
              'with provisional RX mapping. No measured beam pattern or rejection threshold. Fitted TLE timing applied.'),indent=2))
    print(json.dumps([{k:v for k,v in a.items() if k not in ('time_s','azimuth_deg','elevation_deg','east_component','near_time_other_rx')} for a in angles],indent=2))


if __name__=='__main__':run()
