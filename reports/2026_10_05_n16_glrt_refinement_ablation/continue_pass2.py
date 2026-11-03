"""Consolidate complete immutable IQ checkpoints, then fit available scans.

Allows bounded numeric work to overlap the much slower IQ read/scoring stage.
Never publishes a partial refinement as a complete measurement population.
"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor

import pipeline as p
from refinement import winners


def assemble(scan):
    folder=p.HERE/'refinement'/scan
    target=folder/'refined.json'
    if target.exists():
        frozen=folder/'frozen-refined.json'
        if not frozen.exists():frozen.write_bytes(target.read_bytes())
        return True
    original=json.loads((p.calibration.INPUTS/scan/'observations.json').read_text())
    expected={r['probe_key'][0] for r in original['records']}
    paths=list(folder.glob('visit-*.json'))
    found={int(path.stem.split('-')[1]) for path in paths}
    if found!=expected:return False
    visits=[json.loads(path.read_text()) for path in paths]
    signature=visits[0]['signature'];assert all(v['signature']==signature for v in visits)
    records=sorted([r for v in visits for r in v['records']],key=lambda r:r['row_index'])
    assert [r['row_index'] for r in records]==[r['row_index'] for r in original['records']]
    parent=p.calibration.INPUTS/scan/'refinement/refined.json'
    assert signature['parent_sha256']==p.digest(parent)
    summary=dict(status='complete',signature=signature,parent_sha256=signature['parent_sha256'],
        total_candidates=len(records),completed_candidates=len(records),visits=len(visits),
        scorer_calls=sum(v['scorer_calls'] for v in visits),compute_s=sum(v['elapsed_s'] for v in visits),
        retained_previous=sum(r['additional_pass']['retained_previous'] for r in records),
        parity_verified_visits=sum(bool(v['parity_rows']) for v in visits),orbit_information_used=False)
    with target.open('x') as f:json.dump(dict(summary=summary,records=records,top_rows=winners(records)),f,allow_nan=False)
    (folder/'frozen-refined.json').write_bytes(target.read_bytes())
    print('ASSEMBLED',scan,len(records),flush=True);return True


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--maximum-seconds',type=float,default=2400.)
    args=parser.parse_args();begun=time.monotonic();submitted={}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        while len(submitted)<len(p.SCANS):
            for scan in p.SCANS:
                first=p.HERE/'pass1'/scan/'position-zero-c.json'
                raw=p.HERE/'raw'/scan/'position-zero-c.json'
                if scan not in submitted and first.exists() and raw.exists() and assemble(scan):
                    submitted[scan]=pool.submit(p.run,(scan,'pass2'))
                if scan in submitted and submitted[scan].done():submitted[scan].result()
            if len(submitted)==len(p.SCANS):break
            if time.monotonic()-begun>args.maximum_seconds:
                raise TimeoutError('Bounded waiting expired; completed scans/checkpoints are preserved')
            time.sleep(10.)
        for future in submitted.values():future.result()
