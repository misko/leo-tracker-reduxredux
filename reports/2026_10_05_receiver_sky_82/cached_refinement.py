"""Cache immutable capture inspection per worker; unchanged GLRT computation.

The baseline worker reopens and reparses the same recording manifest for every
visit. This adapter reuses its read-only store and inspected capture. IQ still
comes through read_visit_ci16; no constructed IQ paths or cross-probe reuse.
"""
import atexit
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent/'2026_10_04_ds13_18_scan_benchmark'
sys.path.insert(0,str(BENCH))
import run_refinement as baseline

BASE_WORKER = baseline.worker
_stores = {}


class CachedReadPort:
    def __init__(self, store):
        self.store = store
        self.published = {}

    def inspect(self, session):
        if session not in self.published:
            self.published[session] = self.store.inspect(session)
        return self.published[session]

    def read_visit_ci16(self, published, ordinal):
        return self.store.read_visit_ci16(published, ordinal)

    def close(self):
        # Actual store lifetime is the numerical worker, not a single visit.
        pass


def cached_worker(task):
    import leo.storage.adaptive_hop as module
    cls = module.AdaptiveHopIqStore
    key = task[0]['session_id']
    if key not in _stores:
        actual = cls(Path('/srv/bulk/leo'),read_only=True)
        _stores[key] = CachedReadPort(actual)
        atexit.register(actual.close)
    def readonly_factory(root, *, read_only):
        if Path(root) != Path('/srv/bulk/leo') or read_only is not True:
            raise ValueError('cached port only supports the fixed read-only input store')
        return _stores[key]
    # Narrow process-local injection into the unchanged baseline worker. Each
    # process handles one visit at a time; no shared-thread monkeypatching.
    module.AdaptiveHopIqStore = readonly_factory
    try:
        return BASE_WORKER(task)
    finally:
        module.AdaptiveHopIqStore = cls


def scientific_rows(result):
    return [{k:v for k,v in r.items() if k!='refinement_seconds'} for r in result['records']]


def parity(observations):
    data=json.loads(observations.read_text())
    visits=sorted({r['probe_key'][0] for r in data['records']})[:2]
    signature=dict(session_id=data['summary']['session_id'],manifest_sha256=data['signature']['manifest_sha256'])
    times=[]
    for visit in visits:
        rows=[r for r in data['records'] if r['probe_key'][0]==visit]
        task=(signature,visit,rows)
        start=time.monotonic(); cold=BASE_WORKER(task); cold_s=time.monotonic()-start
        start=time.monotonic(); warm=cached_worker(task); warm_s=time.monotonic()-start
        if scientific_rows(cold)!=scientific_rows(warm):
            raise AssertionError('cached input access changed scientific output')
        times.append(dict(visit=visit,candidates=len(rows),cold_s=cold_s,cached_s=warm_s))
    result=dict(session_id=signature['session_id'],exact_scientific_parity=True,visits=times,
                implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(json.dumps(result),flush=True)
    return result


def main(observations):
    folder=observations.parent/'refinement'
    folder.mkdir(exist_ok=True)
    signature=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    parity_path=folder/'cache-parity.json'
    if not parity_path.exists() or json.loads(parity_path.read_text())['implementation_sha256']!=signature:
        parity_path.write_text(json.dumps(parity(observations),indent=2))
    baseline.worker=cached_worker
    sys.argv=['run_refinement',str(observations),'--workers','2']
    try:
        baseline.main()
    finally:
        baseline.worker=BASE_WORKER
    receipt=dict(adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        baseline_worker_sha256=hashlib.sha256(Path(baseline.__file__).read_bytes()).hexdigest(),
        parity_receipt_sha256=hashlib.sha256(parity_path.read_bytes()).hexdigest(),
        scope=__doc__,checkpoint_policy='Baseline scientific/source signatures remain checked. Existing baseline visit checkpoints are reused; execution differs only by immutable metadata caching.')
    (folder/'cache-adapter-receipt.json').write_text(json.dumps(receipt,indent=2))
    result_path=folder/'refined.json'
    if result_path.exists():
        result=json.loads(result_path.read_text())
        result['execution_adapter']=receipt
        result_path.write_text(json.dumps(result,allow_nan=False))
