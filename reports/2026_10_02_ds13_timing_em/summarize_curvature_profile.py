"""Export score tables and verify gradients and capture pose provenance."""
import csv
import json
from pathlib import Path

import numpy as np
from curvature_position_profile import ROOT


def run(directory):
    from position_profile_grid import geodesic_position
    from check_capture_pointing import digest
    from finite_set_fit import assert_snapshot_unchanged, snapshot_files
    source = directory/'receipt.json'
    receipt = json.loads(source.read_text())
    assert_snapshot_unchanged(receipt['source_hashes'])
    evidence_path = ROOT/'prior-position-audit/pointing-evidence.json'
    evidence = json.loads(evidence_path.read_text())
    rows, checks = [], []
    for result in receipt['results']:
        label=result['scan']
        capture=next(c for c in evidence['captures'] if c['scan']==label)
        assert capture['bindings_verified']
        assert digest(Path(capture['path']).read_bytes())==capture['sha256']
        pose=capture['pose']['pose_authority']
        np.testing.assert_allclose(result['roof_lat_lon'],[pose['latitude_deg'],pose['longitude_deg']],rtol=0,atol=1e-12)
        lat,lon=result['roof_lat_lon']
        # Chain-rule conversion from optimizer's fixed regional map to local EN meters.
        jac=np.column_stack([(geodesic_position(lat,lon,b,1)-geodesic_position(lat,lon,b+180,1))/2
                             for b in (90.,0.)])
        for variant, item in result['variants'].items():
            actual_variant='unfiltered' if item.get('identical_to_unfiltered') else variant
            fit=json.loads((directory/f'{label}-{actual_variant}-roof.json').read_text())
            analytic=np.asarray(fit['free_position_gradient'])@jac
            fd=np.asarray(item['derivatives'][0]['gradient_score_per_m'])
            fd100=np.asarray(item['derivatives'][1]['gradient_score_per_m'])
            np.testing.assert_allclose(analytic,fd,rtol=.01,atol=2e-5)
            np.testing.assert_allclose(fd,fd100,rtol=.01,atol=2e-5)
            checks.append(dict(scan=label,variant=variant,analytic_gradient_score_per_m=analytic.tolist(),
                               finite_difference_50m=fd.tolist(),finite_difference_100m=fd100.tolist(),
                               max_nuisance_gradient=max(c['nuisance_gradient'] for c in item['cells'])))
            for c in item['cells']:
                rows.append(dict(scan=label,variant=variant,**{k:c[k] for k in
                    ('label','east_m','north_m','objective','delta_score')}))
    for variant,item in receipt['combined'].items():
        rows.extend(dict(scan='combined',variant=variant,**c) for c in item['cells'])
    with (directory/'scores.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (directory/'verification.json').write_text(json.dumps(dict(checks=checks,capture_pose_hashes_verified=True,
        source_hashes=snapshot_files([__file__,source,evidence_path])),indent=2))
    for r in receipt['results']:
        print(r['scan'],'excluded',r['excluded'])
        for v,item in r['variants'].items():
            print(v, 'gradient',item['derivatives'],'best',item['best']['label'],item['best']['delta_score'])
    print('combined',json.dumps({v:{'derivatives':i['derivatives'],'best':i['best']} for v,i in receipt['combined'].items()},indent=2))


if __name__=='__main__':
    run(ROOT/'curvature-filter-roof-profile')
