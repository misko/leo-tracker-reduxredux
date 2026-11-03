"""Disjoint-recording confirmation of unchanged predictive-noise inference."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import random

import probe_ds23_hierarchical_predictive as engine
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT=ROOT/'reports/2026_10_20_ds23_hierarchical_predictive_validation'


def job(case):
    engine.OUT=OUT
    return engine.run(case)


def main():
    if (OUT/'execution.json').exists():raise FileExistsError('preserve completed confirmation')
    OUT.mkdir(exist_ok=True)
    development=read(engine.OUT/'protocol.json')
    pool=sorted(set(read(ROOT/'reports/2026_10_20_ds23_skew_phase_full/protocol.json')['cases'])-set(development['cases']))
    cases=random.Random(2026102007).sample(pool,20)
    protocol=dict(development,cases=cases,selection_seed=2026102007,
        available_pool=pool,disjoint_from_first20_recordings=True,
        same_site_not_external_geographic_or_temporal_block_validation=True,
        first20_protocol_sha256=sha(engine.OUT/'protocol.json'),
        same_inference_priors_noise_gates_masks_and_search_budget=True,
        adapter_sha256=sha(ROOT/'tools/validate_ds23_hierarchical_predictive.py'))
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('confirmation selection changed')
    write(path,protocol)
    receipts=[]
    with ProcessPoolExecutor(max_workers=20) as pool:
        futures={pool.submit(job,c):c for c in cases}
        for future in as_completed(futures):
            try:receipts.append(future.result())
            except Exception as exc:receipts.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(completed=len(receipts),total=len(futures),receipts=receipts))
    write(OUT/'execution.json',dict(all_terminal=True,receipts=receipts))


if __name__=='__main__':main()
