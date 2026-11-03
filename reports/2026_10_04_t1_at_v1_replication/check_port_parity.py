"""Numerical oracle audit of the new storage-free production selection core.

Not production inference. Frozen historical pools are test-only oracles; they
are never imported by the production component. CFO values are not consumed
by selection (pool residuals are); only its discrete assignments are audited.
"""
import json
from pathlib import Path
import sys
import time
import numpy as np
from run import TopAbsoluteCalibration, digest

WORKTREE=Path('/srv/bulk/leo-dev/t1-at-integration-LxiJ1v')
sys.path.insert(0,str(WORKTREE/'src'))
from leo.analysis.t1_at import _Search
from leo.contracts.t1_at import T1AtCandidateV1, T1AtModeV1

HERE=Path(__file__).resolve().parent
BASE=Path('/srv/bulk/leo/t1-at-v1-replication-20261004')
INPUTS=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
LEGACY=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')


def run(scan):
    folder=BASE/('replayed-ab-verified' if scan in ('A','B') else 'attempt2' if scan in ('N01','N02') else 'remaining')/scan
    pool_path=(LEGACY/('full-scan-A-refinement/top-one' if scan=='A' else 'position-top-2km/B-top')/'candidate-pool.json') if scan in ('A','B') else folder/'candidate-pool.json'
    pool=json.loads(pool_path.read_text());original=np.array(pool['original_rows'])
    if scan in ('A','B'):
        with np.load(HERE.parent/f'2026_10_03_ds13_coverage_goal/frozen/{scan}-observations.npz') as z:
            times,rx,ch,groups=[z[k][original] for k in ('times_s','receiver','channel','group')]
    else:
        cal=TopAbsoluteCalibration(INPUTS/scan/'seed-timing-v6');data=cal.data
        assert np.array_equal(data.original_rows,original)
        times,rx,ch,groups=data.times,data.receiver,data.channel,data.group
    candidates=tuple(T1AtCandidateV1(candidate_id=int(r),window_id=str(g),receiver_id=int(a),
        channel=int(b),receive_time_s=float(t),refined_cfo_hz=0.,refined_margin=0.)
        for r,g,a,b,t in zip(original,groups,rx,ch,times))
    rows=[]
    for arm in ('fitted-c','zero-c'):
        modes=tuple(T1AtModeV1(catalog_number=m['catalog_number'],absolute_timing_s=m['offset_s'],
            candidate_ids=tuple(map(int,original[m['eligible_rows']])),residual_hz=tuple(m['residual_hz'])) for m in pool['arms'][arm])
        result=_Search(candidates,modes,time.monotonic()+180).run()
        oracle=json.loads((folder/f'{arm}.json').read_text())
        for stage in ('initial','final'):
            a=result[stage];b=oracle[stage]
            actual={x['candidate_id']:(x['catalog_number'],x['mode_index'],x['residual_hz']) for x in a['assignments']}
            expected={x['row_index']:(x['catalog_number'],x['mode_index'],x['residual_hz']) for x in b['assignments']}
            assert actual==expected,(scan,arm,stage,'assignments differ')
            assert a['objective']==b['objective'],(scan,arm,stage,'objective differs')
        rows.append(dict(scan=scan,arm=arm,assigned=result['final']['assigned'],exact_assignments=True,
                         oracle_sha256=digest((folder/f'{arm}.json').read_bytes()),pool_sha256=digest(pool_path.read_bytes())))
    return rows


if __name__=='__main__':
    rows=[]
    for scan in ['A','B']+[f'N{i:02}' for i in range(1,17)]:
        rows.extend(run(scan)); print(scan,'parity passed',flush=True)
        (HERE/'production-core-parity.json').write_text(json.dumps(dict(scope=__doc__,
            core_sha256=digest((WORKTREE/'src/leo/analysis/t1_at.py').read_bytes()),rows=rows),indent=2))
