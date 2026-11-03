"""Verify stored pair statistics and add rank-based descriptive checks."""
import json
from pathlib import Path
import hashlib

import numpy as np
from scipy.stats import spearmanr

HERE=Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    result=[]
    paths=[Path(__file__)]
    for index in (0,16):
        path=HERE/f'{index:02d}.json'; paths.append(path)
        artifact=json.loads(path.read_text())
        for p,h in artifact['sources'].items():
            assert digest(p)==h,p
        for arm,pairs in artifact['results'].items():
            for pair in pairs:
                rows=pair['rows']
                assert len({r['left_index'] for r in rows})==len(rows)==len({r['right_index'] for r in rows})
                assert all(abs(r['time_difference_s'])<=.25 for r in rows)
                if len(rows)<6:
                    assert pair['residual_statistics'] is None
                    continue
                left=np.array([r['left_residual_hz'] for r in rows])
                right=np.array([r['right_residual_hz'] for r in rows])
                delta=left-right
                independent=float(np.sqrt(np.mean((delta-np.median(delta))**2)))
                assert abs(independent-pair['residual_statistics']['centered_difference_rms_hz'])<1e-10
                a,b=left-np.median(left),right-np.median(right)
                result.append(dict(scan_index=index,arm=arm,matches=len(rows),
                                   spearman=float(spearmanr(left,right).statistic),
                                   median_absolute_common_hz=float(np.median(abs((a+b)/2))),
                                   median_absolute_differential_hz=float(np.median(abs((a-b)/2)))))
    output=dict(schema='ds11-source-pair-verification/v1',verified=True,rank_diagnostics=result,
                sources={str(p):digest(p) for p in paths})
    with (HERE/'verification.json').open('x') as stream:
        json.dump(output,stream,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
