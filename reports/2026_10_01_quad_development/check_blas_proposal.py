"""Bounded full-grid proposal equivalence against a sealed baseline receipt."""
import argparse
import json
from pathlib import Path
import resource
import time
import numpy as np
from run_window import prepare_window
from acquire_blas import acquire_blas
from regression_batch import digest,verify_sources

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('unit');args=parser.parse_args()
block=args.unit.rsplit('-',1)[0]
path=HERE/'independent-v2'/block/(args.unit+'.json')
assert digest(path)==path.with_suffix('.sha256').read_text().strip()
parent=json.loads(path.read_text());verify_sources(parent['source_sha256']);verify_sources(parent['inputs'])
binding,scans,_,_,_=prepare_window(args.unit)
before=time.process_time();started=time.monotonic()
seeds,proposal=acquire_blas(scans,started+50*binding['size'])
elapsed=time.monotonic()-started;cpu=time.process_time()-before
expected=parent['proposal']
assert proposal['requested']==expected['requested'] and proposal['unique_points']==expected['unique_points']
assert proposal['spacing']==expected['spacing']
np.testing.assert_array_equal(proposal['seeds'],expected['seeds'])
error=float(np.max(abs(np.asarray(proposal['scores'])-expected['scores'])))
assert error<1e-6,error
result=dict(unit=args.unit,seed_coordinates_exact=True,score_max_error=error,
    requested=proposal['requested'],unique_points=proposal['unique_points'],proposal_seconds=elapsed,
    proposal_cpu_seconds=cpu,parent_sha256=digest(path),source_sha256={str(p):digest(p) for p in
    [Path(__file__),HERE/'acquire_blas.py',HERE/'acquisition_blas.py',HERE.parents[1]/'src/leo/analysis/localization_geometry_blas.py']},
    qualification='Full adaptive-grid proposal check only. Identical seed coordinates, order and point counts; bounded floating score differences. No joint fit, new geographic result or cold-pipeline speedup claim.')
out=HERE/('blas-proposal-'+args.unit+'-v1.json')
with out.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
out.with_suffix('.sha256').write_text(digest(out)+'\n')
print(json.dumps(result,indent=2))
