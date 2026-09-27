"""Check every shortlisted candidate offset at both corrected fit winners."""
import json
import time
import numpy as np
import refit
from solver import fit,reference
HERE=refit.HERE
started=time.monotonic();refit.old.HERE=HERE/'refit';model=refit.old.Model();rows=[]
for arm in ['cfo_only','phase']:
    source=HERE/'refit'/f'{arm}.json';result=json.loads(source.read_text());assert result['complete'];x=result['best']['x'];lat,lon=model.coordinates(x);rec=refit.old.geo.geodetic_to_ecef_km(lat,lon,0);count=0;worst=0.;bad=0
    for si,bank in enumerate(model.banks):
        for b in bank['tracks'].values():
            p,v,ids=refit.old.geo.propagate_candidate_states(bank['cat'],b['ids'],bank['start'],b['times'],np.array([x[si+2]]));assert np.array_equal(ids,b['ids']);d=p[:,0]-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);n=len(b['mask']);pred=-refit.old.geo.REFERENCE_RF_HZ/refit.old.geo.LIGHT_KM_S*np.sum(d[:,:n]*v[:,0,:n],axis=-1);train=(np.array(b['t']['measured_hz'])-pred)[:,b['mask']];offset,_=fit(train)
            for values,o in zip(train,offset):
                expected,check=reference.fit(values);assert check['converged'];loss=lambda z:2.5*np.log1p((values-z)**2/40000).sum()+.5*(z/1e6)**2
                difference=float(loss(o)-loss(expected));worst=max(worst,abs(difference));bad+=abs(difference)>1e-6;count+=1
    rows.append(dict(arm=arm,fit_sha256=refit.old.joint.sha(source),candidates=count,maximum_loss_difference=worst,mismatches=bad));print(rows[-1],flush=True)
(HERE/'refit/offset-audit.json').write_text(json.dumps(dict(complete=True,rows=rows,elapsed_s=time.monotonic()-started),indent=2)+'\n')
