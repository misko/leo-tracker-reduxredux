"""Read saved incumbent control geometry after measurement seal; never refit."""
import hashlib
import json
from pathlib import Path
import numpy as np
from diagnose_all_large_tracks import context

OUT=Path(__file__).resolve().parent


def read(p):return json.loads(Path(p).read_text())


def main():
    measurement=read(OUT/'raw-pilot-measurements.json');seal=read(OUT/'raw-pilot-measurement-seal.json')
    assert hashlib.sha256((OUT/'raw-pilot-measurements.json').read_bytes()).hexdigest()==seal['measurement_sha256']
    plan=read(OUT/'raw-plan.json');rows=[r for r in measurement['rows'] if r['kind']=='other_family_control']
    inv=Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/cases/DS26-0265/candidate-v2/recovery/all-large-track-recovery/91df73bf7f196522ac9bebfe15c91fa3/inventory.json')
    d=context(read(inv));result=dict(scope='Reporting-only6controlpoints at existing original incumbent geometry; inherited curved conditional residuals. Same immutable measurement seal. No fit, position/bias/phase update or independent frequency truth.',
        measurement_seal=seal,inventory_sha256=hashlib.sha256(inv.read_bytes()).hexdigest(),arms={})
    for arm,(p,x) in d['problems'].items():
        calc=p.calculate(x);lookup={}
        for i,sl in zip(p.members,p.slices,strict=True):
            t=d['scan'].tracks[i]
            for k,oid in enumerate(t['observation_ids']):
                lookup[oid]=(sl.start+k,t['key'])
        records=[]
        for row in rows:
            ix,component=lookup[row['observation_id']];assert p.keep[ix]
            before=float(calc['conditional_residual_hz'][ix]);after=before+row['subbin_CFO_delta_hz']
            records.append(dict(observation_id=row['observation_id'],component=component,visit_index=row['visit_index'],
                original_residual_hz=before,continuous_residual_hz=after,CFO_delta_hz=row['subbin_CFO_delta_hz']))
        result['arms'][arm]=dict(endpoint_east_north_km=x.tolist(),baseline_objective_replay_difference=d['replay'][arm],rows=records,
            before_RMS_hz=float(np.sqrt(np.mean([r['original_residual_hz']**2 for r in records]))),
            after_RMS_hz=float(np.sqrt(np.mean([r['continuous_residual_hz']**2 for r in records]))))
    (OUT/'raw-controls-reporting.json').write_text(json.dumps(result,indent=2)+'\n')
    for arm,r in result['arms'].items():print(arm,r['before_RMS_hz'],r['after_RMS_hz'])


if __name__=='__main__':main()
