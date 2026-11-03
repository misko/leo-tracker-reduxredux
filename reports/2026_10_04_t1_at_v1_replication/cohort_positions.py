"""All 18 independent scans; matched RF arms and cumulative roof-RMS cuts."""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import subset_positions as positions
from cohort import digest

LEGACY = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
ASSOC = Path('/srv/bulk/leo/t1-at-v1-replication-20261004')


def prepare(scan):
    if scan.startswith('N'):
        positions.ASSOCIATIONS = ASSOC/('attempt2' if scan in ('N01','N02') else 'remaining')
        positions.prepare(scan)
        return
    target = positions.ROOT/scan/'input.npz'
    if target.exists(): return
    source = LEGACY/f'position-top-2km/{scan}-profile-input.npz'
    metadata = json.loads(source.with_suffix('.json').read_text())
    association = ASSOC/'replayed-ab-verified'/scan/'fitted-c.json'
    result = json.loads(association.read_text())
    assignments = sorted(result['final']['assignments'],key=lambda a:a['row_index'])
    with np.load(source) as z: full = {k:z[k].copy() for k in z.files}
    lookup={int(r):i for i,r in enumerate(full['original_rows'])}
    ids=np.array([lookup[a['row_index']] for a in assignments])
    fields=('times','measured','rf','receiver','channel','group','margin','original_rows','fixed_receiver_hz')
    data={k:(v[ids] if k in fields else v) for k,v in full.items() if k!='raw_refined_hz'}
    data['owners']=np.array([a['catalog_number'] for a in assignments])
    refined=LEGACY/('full-scan-A-refinement/refined.json' if scan=='A' else 'position-top-2km/B-refinement/refined.json')
    margins={r['row_index']:r['refinement'].get('margin',r['original_margin']) for r in json.loads(refined.read_text())['records']}
    data['margin']=np.array([margins[int(r)] for r in data['original_rows']])
    assert set(data['owners']) == set(data['numbers'])
    target.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(target,**data)
    positions.save(target.with_suffix('.json'),dict(scan=scan,scope=positions.__doc__,
        sources={str(p):digest(p.read_bytes()) for p in (source,source.with_suffix('.json'),association,refined)},
        input_sha256=digest(target.read_bytes()),seed_coefficient=metadata['seed_coefficient_hz_per_ghz'],
        rf_center_hz=float(np.mean(np.unique(full['rf']))),historical_preparation_metadata=metadata))


def task(job):
    prepare(job[0])
    return positions.run_case(job)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scans',nargs='+',default=['A','B']+[f'N{i:02}' for i in range(1,17)])
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        # Finish the shared roof rankings before submitting dependent subsets.
        pending={pool.submit(task,(s,'support',1.)):s for s in args.scans}
        while pending:
            future=next(as_completed(pending))
            scan=pending.pop(future)
            print('DONE',future.result(),flush=True)
            if scan is not None:
                jobs=[(scan,r,f) for r in ('rms','support','glrt') for f in (.25,.5,.75)]
                jobs += [(scan,'rms-cut',cut) for cut in (50,100,300,600)]
                for job in jobs: pending[pool.submit(task,job)]=None
