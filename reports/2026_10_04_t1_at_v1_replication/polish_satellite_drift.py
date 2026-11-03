"""Equal final continuation for every control/drift and fitted/zero-c case."""
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from satellite_drift_localization import (OUT,SCANS,ARMS,MODES,load,SatelliteDriftObjective,
    diagnostics,fit,best_record,digest,serial)

POLISHED = OUT/'polished'
BUDGET_S = 30.


def run(task):
    scan,arm,mode = task
    source = OUT/f'{scan}-{arm}-{mode}.json'
    target = POLISHED/source.name
    if target.exists():return str(target)
    data,meta,_ = load(scan)
    r = json.loads(source.read_text())
    obj = SatelliteDriftObjective(data,meta['rf_center_hz'],arm,mode)
    before = r['best']
    new = fit(obj,np.asarray(before['vector']),before['point_km'],BUDGET_S,radius_km=4.)
    new.update(stage='matched-final-continuation',satellite_drift_hz_s=new['vector'][obj.size:-1])
    r['records'].append(new)
    r['best'] = best_record(r['records'])
    r.update(diagnostics(obj,data,r['best']))
    assert r['objective']<=before['objective']+1e-7
    r.update(pre_polish_source_sha256=digest(source),extra_polish_budget_s=BUDGET_S,
        polish_implementation_sha256=digest(Path(__file__)))
    target.write_text(json.dumps(r,default=serial,indent=2,allow_nan=False))
    print('DRIFT POLISH',scan,arm,mode,round(r['distance_m']),r['converged'],r['kkt'],flush=True)
    return str(target)


if __name__=='__main__':
    POLISHED.mkdir(exist_ok=True)
    tasks = [(s,a,m) for s in SCANS for a in ARMS for m in MODES]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,t) for t in tasks]):f.result()
