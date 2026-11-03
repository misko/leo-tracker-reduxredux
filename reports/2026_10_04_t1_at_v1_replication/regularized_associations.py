"""Matched full-top-window selection: historical T1-AT versus timing regularization.

Reuse the exact archived candidate pool, GLRT refinement, nuisance predictions,
600 Hz gate, lane coherence and replacement neighborhood. No new folds or RF
data collection. Existing upstream fold-derived calibration remains frozen.
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from run import LEGACY,HERE
from numeric_data import load
from timing_bound_comparison import digest
from subset_positions import serial
from timing_selection_score import TimingPriorMixin

sys.path.insert(0,str(LEGACY))
import greedy_pool_two_scans as historical
sys.path.insert(0,str(historical.OLD))
from penalty_replace_search import Search
from greedy_restart_scan import compile_mode

OUT=HERE/'timing-regularized-selection'
INPUTS=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
OLD_INPUTS=Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')
SCANS=tuple(f'N{i:02}' for i in range(1,17))
ARMS=('fitted-c','zero-c')
MODES={'count-control':0.,'timing-regularized':1.}


class TimingSearch(TimingPriorMixin,Search):pass


def run(scan):
    meta=json.loads((OLD_INPUTS/scan/'input.json').read_text())
    prior_path=Path(meta['association_source']);pool_path=prior_path.with_name('candidate-pool.json')
    pool=json.loads(pool_path.read_text());d=load(INPUTS/scan/'seed-timing-v6')
    assert pool['original_rows']==d.original_rows.tolist()
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms'][ARMS[0]]]==[(m['catalog_number'],m['offset_s']) for m in pool['arms'][ARMS[1]]]
    folder=OUT/scan;folder.mkdir(parents=True,exist_ok=True)
    for arm in ARMS:
        old_path=prior_path.with_name(f'{arm}.json');old=json.loads(old_path.read_text())
        modes=[compile_mode(r,d.receiver,d.channel) for r in pool['arms'][arm]]
        for name,weight in MODES.items():
            target=folder/f'{arm}-{name}.json'
            if target.exists():continue
            result=TimingSearch(modes,d.group,d.times,timing_weight=weight).run(3)
            for stage in ('initial','final'):
                r=result[stage]
                for a in r['assignments']:a['row_index']=int(d.original_rows[a['row_index']])
                r.update(denominator=len(d.times),unassigned=len(d.times)-r['assigned'],coverage=r['assigned']/len(d.times))
            reproduced=False
            if weight==0:
                for stage in ('initial','final'):
                    for key in ('assigned','satellites','objective','assignments','selected'):
                        assert result[stage][key]==old[stage][key],(scan,arm,stage,key)
                assert result['passes']==old['passes']
                reproduced=True
            a={x['row_index']:x['catalog_number'] for x in old['final']['assignments']}
            b={x['row_index']:x['catalog_number'] for x in result['final']['assignments']}
            result.update(scope=__doc__,scan=scan,arm=arm,mode=name,timing_weight=weight,
                timing_prior='0.5 sum((tau_s-mean(tau))^2) + 0.5 (mean(tau)/10)^2; common bound +/-10 s',
                interpretation='Regularized coverage units; not an exact frequency-likelihood objective.',
                source_sha256=digest(pool_path),baseline_source_sha256=digest(old_path),
                implementation_sha256={str(p):digest(p) for p in (Path(__file__),HERE/'timing_selection_score.py',LEGACY/'penalty_replace_search.py',LEGACY/'greedy_restart_scan.py')},
                original_rows=d.original_rows,heldout_original_rows=[],baseline_exactly_reproduced=reproduced,
                gained_windows=len(set(b)-set(a)),lost_windows=len(set(a)-set(b)),
                relabeled_windows=sum(a[i]!=b[i] for i in set(a)&set(b)),
                rms_hz=float(np.sqrt(np.mean([x['residual_hz']**2 for x in result['final']['assignments']]))))
            target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
            print('REGULARIZED ASSOCIATION',scan,arm,name,result['final']['assigned'],len(d.times),result['final']['satellites'],flush=True)
    return scan


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,s) for s in SCANS]):print('SCAN DONE',f.result(),flush=True)
