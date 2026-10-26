"""Released saved-number check, using an independent unit-vector distance."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np

ROOT=Path(__file__).resolve().parent.parent
SCI=ROOT/'position'
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    start=time.monotonic();checks=[]
    def check(name,passed):checks.append(dict(name=name,passed=bool(passed)))
    data=read(SCI/'geographic/summary.json');seal=read(SCI/'geographic/seal.json')
    check('RF audit passed before explicitly released geographic evaluator',
        read(ROOT/'audit/position_terminal.json')['all_passed'] and
        data['root_release']=='explicit coordinator message after passing RF terminal audit')
    check('all frozen evaluator and geographic output hashes exact',
        all(sha(p)==h for p,h in seal['files'].items()))
    saved=read('/srv/bulk/leo/research/ds25-20261024/family_cavity/position/DS24-0011.json')['policy_arms']
    reference=data['reference_latlon']
    def point(x):return [37.906+x[1]/111.,-122.545+x[0]/(111.32*np.cos(np.deg2rad(37.906)))]
    def unit(ll):
        lat,lon=np.deg2rad(ll);return np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
    def distance(ll):
        a,b=unit(reference),unit(ll);return float(6371.0088*np.arctan2(np.linalg.norm(np.cross(a,b)),a@b))
    check('six declared slots/four completed endpoints/no mixture epoch substitution',
        data['declared_slots']==6 and data['completed_final_endpoints']==4 and data['mixture_final_endpoints']==0 and len(data['rows'])==6)
    for row in data['rows']:
        baseline=distance(point(saved[row['arm']]['endpoint_east_north_km']))
        check(row['arm']+'/'+row['method']+': exact original baseline operational fallback and unqualified source',
            abs(baseline-row['original_reference_error_km'])<1e-8 and
            row['operational_policy_error_km']==row['original_reference_error_km'] and
            not row['target_association_qualified'] and not row['partial_epoch_substituted'])
        if row['final_endpoint_available']:
            raw=read(SCI/row['arm']/row['method']/'raw_endpoint.json')
            expected=distance(point(raw['endpoint_east_north_km']))
            check(row['arm']+'/'+row['method']+': completed raw endpoint distance and reference difference',
                abs(expected-row['raw_position_error_km'])<1e-8 and
                abs(1000*(expected-baseline)-row['raw_error_minus_reference_m'])<1e-5)
        else:
            check(row['arm']+'/mixture: missing endpoint remains null',row['method']=='mixture' and
                row['raw_position_error_km'] is None and row['raw_error_minus_reference_m'] is None)
    result=dict(all_passed=all(r['passed'] for r in checks),checks=checks,seconds=time.monotonic()-start,
        source_sha256=sha(__file__),geographic_seal_sha256=sha(SCI/'geographic/seal.json'),
        new_fits=0,orbit_propagation_calls=0,evaluation_scope='After root release only. Four completed raw endpoints; no operational change and no mixture final result.')
    with (ROOT/'audit/geographic_readback.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'],checks=len(checks),seconds=result['seconds'])))


if __name__=='__main__':main()
