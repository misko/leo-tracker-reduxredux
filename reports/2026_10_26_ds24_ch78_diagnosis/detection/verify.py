"""No-IQ verification of owned tests, hashes, complete cells and parity."""
import os
from pathlib import Path
import sys
import time
import unittest
from study import HERE, read, sha, dump, replay

began=time.monotonic()
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_study.py')
result=unittest.TextTestRunner(verbosity=2,stream=sys.stderr).run(suite)
protocol=read(HERE/'protocol.json')
data=read(HERE/'results.json')
diagnostic=read(HERE/'diagnostic.json')
summary=read(HERE/'summary.json')
panel=read(HERE/'panel.json')
attempt=read(HERE/'panel_attempt01.json')
checks=dict(owned_tests_passed=result.wasSuccessful(),tests=result.testsRun,
    frozen_primary_sources_unchanged=all(sha(p)==h for p,h in protocol['files'].items()),
    frozen_diagnostic_sources_unchanged=all(sha(p)==h for p,h in read(HERE/'diagnostic_protocol.json')['files'].items()),
    exact_panel_preserved_during_metadata_amendment=[s['probe']['visit_index'] for s in panel['slots']]
        ==[s['probe']['visit_index'] for s in attempt['slots']],
    all_8_physical_windows=len(data['rows'])==8 and all(r['status']=='complete' for r in data['rows']),
    all_16_native_receivers=len([r for s in data['rows'] for o in s['outcomes'] for r in o['rows']
        if r['label']=='recorded' and r['strength_db'] is None])==16,
    all_64_recorded_injection_cells=summary['observed_recorded_injection_cells']==64,
    exact_primary_parity=summary['parity_all_passed'],
    diagnostic_reproduces_primary=diagnostic['all_export_parity_passed'],
    historical_runtime_still_unchanged=replay.runtime_identity()==protocol['identity'],
    bounded_processes=data['seconds']<580 and diagnostic['seconds']<580 and read(HERE/'probe.json')['seconds']<580,
    no_GPS_or_position_inference=protocol['no_GPS'],
    BLAS1=all(os.environ.get(k)=='1' for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']))
all_passed=all(v for k,v in checks.items() if k!='tests')
files=[p for p in HERE.iterdir() if p.is_file() and p.name!='verification.json']
dump(HERE/'verification.json',dict(all_passed=all_passed,checks=checks,seconds=time.monotonic()-began,
    artifact_sha256={p.name:sha(p) for p in sorted(files)},IQ_reads=0))
print('verification',all_passed,flush=True)
if not all_passed:raise SystemExit(1)
