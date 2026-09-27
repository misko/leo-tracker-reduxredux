"""Check one-second Doppler interpolation at independent off-grid epochs."""
import json
from pathlib import Path
import numpy as np
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km
root=Path(__file__).resolve().parent;data=json.loads((root/'inputs.json').read_text())
archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshot=archive.select_latest_before(data['start_utc_ns']-505_000_000_000);assert snapshot.digest==data['snapshot_digest']
payload,_=exclude_labelled_starlink_debris(archive.read(snapshot));cat=parse_element_sets(payload)
query=np.array([17.123,72.456,151.789,213.3783336,287.321]);epochs=np.concatenate([query,np.floor(query),np.floor(query)+1])
p,v,ids=propagate_candidate_states(cat,np.arange(len(cat.satellite_numbers)),data['start_utc_ns'],epochs,np.array([0.]));p=p[:,0];v=v[:,0]
receiver=geodetic_to_ecef_km(38.4,-122.,0);lat,lon=np.radians([38.4,-122.]);up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
dr=p-receiver;u=dr/np.linalg.norm(dr,axis=-1)[...,None];doppler=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(u*v,axis=-1)
w=query%1;interpolated=doppler[:,5:10]*(1-w)+doppler[:,10:]*w;mask=np.sum(u[:,:5]*up,axis=-1)>0;error=(interpolated-doppler[:,:5])[mask]
out=dict(epochs_s=query.tolist(),observer_scenario=[38.4,-122.,0],visible_candidate_epochs=len(error),rms_error_hz=float(np.sqrt(np.mean(error**2))),maximum_absolute_error_hz=float(np.max(abs(error))),p99_absolute_error_hz=float(np.quantile(abs(error),.99)),scope='Five off-grid times at a fixed regional scenario point; not a global interpolation error bound')
(root/'interpolation-check.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
