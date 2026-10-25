"""Fixed 60108 nominal-bank visibility only; no measured CFO or position fit."""
from pathlib import Path
import hashlib
import json
import math
import signal
import time

import numpy as np
import geometry_support_snapshot as support
from leo.analysis.research.orbit_phase_geometry import phase_shifted_states, EARTH_ROTATION_RAD_S
from leo.sky.frames import geodetic_to_ecef_km, ecef_to_enu_matrix, look_angles

HERE=Path(__file__).resolve().parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024/DS24-0013')
PARENT=SOURCE.parent/'family_cavity/position/DS24-0013.json'
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')


def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encode(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)
def write(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2,allow_nan=False,default=encode);f.write('\n')


def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('30s fixed hypothesis geometry cap')))
    signal.setitimer(signal.ITIMER_REAL,30.)
    files=[Path(__file__),HERE/'geometry_support_snapshot.py',HERE/'test_geometry_visibility.py',
        HERE.parent/'scientific/support_geometry.py',HERE/'whole_scan_inventory.json',HERE/'whole_scan_seal.json',
        SOURCE/'bank.npz',SOURCE/'receipt.json',SOURCE/'nominal_elements.json',SOURCE/'selected.tle',PARENT,
        REPO/'src/leo/analysis/research/orbit_phase_geometry.py',REPO/'src/leo/sky/frames.py',
        REPO/'tools/prototype_dsx01_continuous_position.py']
    bindings={str(p):sha(p) for p in files}
    assert sha(HERE/'geometry_support_snapshot.py')==sha(HERE.parent/'scientific/support_geometry.py')
    assert tuple(support.DOMAIN)==(-15.,15.) and support.OMEGA==EARTH_ROTATION_RAD_S
    protocol=dict(hypothesis_norad=60108,selected_owners='ALL3 frozen whole-scan unused curved RX2 sources; no backfill',
        fixed_position='saved original policy_arms.c0 RF endpoint, not evaluation site',
        phase_domain_s=[-15.,15.],altitude_m=0.,
        nominal_event='visibility of original linearly interpolated causal bank with Earth-rotation phase correction at ALL original native times',
        certification='unchanged source-bound support_geometry.support; empty only if certified and no inner/possible-root interval',
        scope_limit='not visibility integrated over Gaussian physical modes, true orbit truth or calibrated GLRT detection',
        input_source_bindings=bindings,maximum_seconds=30,workers=1,BLAS_threads=1,
        new_CFO_scores=0,position_fits=0,GPS_used=False,operational_association=False)
    write(HERE/'geometry_protocol.json',protocol)
    previous=read(HERE/'whole_scan_inventory.json')
    assert previous['selected_count']==3 and previous['selected_distinct_native_IDs']==124
    assert all(sha(HERE/n)==h for n,h in read(HERE/'whole_scan_seal.json')['files'].items())
    receipt=read(SOURCE/'receipt.json');elements=read(SOURCE/'nominal_elements.json')
    assert sha(SOURCE/'bank.npz')==receipt['bank_sha256']
    assert sha(SOURCE/'selected.tle')==receipt['latest_tle_sha256']
    assert receipt['cutoff_utc_ns']<=receipt['origin_utc_ns']
    provenance=elements['60108']['provenance']
    assert max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])<=receipt['cutoff_utc_ns']
    parent=read(PARENT);x=np.asarray(parent['policy_arms']['c0']['endpoint_east_north_km'],float)
    latitude=37.906+x[1]/111.;longitude=-122.545+x[0]/(111.32*math.cos(math.radians(37.906)))
    observer=geodetic_to_ecef_km(latitude,longitude,0.)
    enu=ecef_to_enu_matrix(latitude,longitude);up=enu[2]
    with np.load(SOURCE/'bank.npz',allow_pickle=False) as z:
        candidates=z['norad'];j=np.flatnonzero(candidates==60108)
        assert len(j)==1
        bank=dict(time_s=z['time_s'],position_km=z['position_km'][j],velocity_km_s=z['velocity_km_s'][j])
    np.savez_compressed(HERE/'geometry_input.npz',**bank,observer_ecef_km=observer,up=up,RF_east_north_km=x)
    rows=[]
    for owner in previous['selected']:
        times=np.asarray(owner['times_s'],float)
        result=support.support(bank,times,up,observer)
        empty=bool(result['certified'] and not result['inner_visible_intervals'] and not result['root_brackets'])
        # Three diagnostic nodes validate the unchanged public phase/ENU port;
        # they are not the visibility certificate.
        checks=[]
        for phi in (-15.,0.,15.):
            position,velocity=phase_shifted_states(bank,times,phi)
            elevation=look_angles(position,velocity,observer,enu)[1][0]
            projection=(position[0]-observer)@up
            assert np.array_equal(elevation>=0,projection>=0)
            checks.append(dict(phase_s=phi,minimum_elevation_deg=float(elevation.min()),maximum_elevation_deg=float(elevation.max())))
        row=dict(component=owner['component'],points=owner['points'],observation_ids=owner['observation_ids'],
            times_s=times,start_s=owner['start_s'],end_s=owner['end_s'],rf_hz=owner['rf_hz'],
            support=result,nominal_complete_owner_support_empty=empty,
            status='certified_empty_nominal_phase_support' if empty else 'certified_nonempty_or_boundary_support' if result['certified'] else 'unresolved',
            diagnostic_nodes_not_certificate=checks)
        rows.append(row);write(HERE/('geometry_'+owner['component'].split('-')[3]+'_'+owner['component'].split('-')[4]+'.json'),row)
    for p,h in bindings.items():assert sha(p)==h,'bound input/source changed during geometry'
    elapsed=time.monotonic()-began
    output=dict(rows=rows,selected_owners=3,selected_native_IDs=124,
        certified_empty_nominal_owners=sum(r['nominal_complete_owner_support_empty'] for r in rows),
        unresolved_owners=sum(r['status']=='unresolved' for r in rows),
        RF_position_east_north_km=x,RF_position_latlon=[latitude,longitude],altitude_m=0.,
        causal_provenance=provenance,cutoff_utc_ns=receipt['cutoff_utc_ns'],
        geometry_input_sha256=sha(HERE/'geometry_input.npz'),protocol_sha256=sha(HERE/'geometry_protocol.json'),
        seconds=elapsed,new_CFO_scores=0,position_fits=0,GPS_used=False,
        physical_mode_visibility_integrated=False,operational_association=False)
    write(HERE/'geometry_result.json',output)
    owned=[p for p in HERE.iterdir() if p.is_file() and p.name.startswith('geometry_') and p.name!='geometry_seal.json']+[HERE/'test_geometry_visibility.py']
    write(HERE/'geometry_seal.json',dict(files={p.name:sha(p) for p in sorted(owned)},new_CFO_scores=0,position_fits=0,GPS_used=False))
    signal.setitimer(signal.ITIMER_REAL,0)
    print(json.dumps({k:v for k,v in output.items() if k not in ('rows','RF_position_east_north_km','RF_position_latlon','causal_provenance')},indent=2))


if __name__=='__main__':main()
