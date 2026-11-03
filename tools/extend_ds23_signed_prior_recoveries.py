"""Apply the unchanged signed-prior policy to isolated timeout recoveries.

Only input-root binding is adapted. Each worker runs the original inference
function in its own process, preserving its scientific priors and budgets.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from algo02_scan import bind_run_directory, load_scan
from investigate_algo01_ds23_0217 import problem
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_algo02_ds23 import DEFAULT_RUN, verify_freeze
from verify_ds23_recovered_positions import RUNS, OUT as RECOVERY

OUT=ROOT/'reports/2026_10_20_ds23_signed_recoveries'
SIGNED=ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'


def prepare():
    verify_freeze(DEFAULT_RUN);OUT.mkdir(exist_ok=True)
    path=OUT/'protocol.json'
    sources=[Path(__file__),ROOT/'tools/probe_ds23_causal_phase_location.py',
        ROOT/'tools/ds23_causal_phase_location.py',ROOT/'tools/probe_ds23_frequency_events.py']
    source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources}
    if path.exists():
        protocol=read(path)
        if protocol['source_sha256']!=source_hashes:raise ValueError('signed recovery source changed')
        return protocol
    replay=read(RECOVERY/'independent_recovery_evaluation.json')
    if not replay['all_verified'] or replay['independently_replayed_recoveries']!=6:
        raise ValueError('all six original pipeline recoveries must independently replay')
    bindings={case:dict(root=str(root.relative_to(ROOT)),
        original_result_sha256=sha(root/case/'algo02_result.json'),
        initial_result_sha256=sha(root/case/'result.json')) for case,root in RUNS.items()}
    protocol=dict(cases=sorted(RUNS),population=413,original_signed_available=404,
        recovered_original_bindings=bindings,source_sha256=source_hashes,workers=6,
        prior_rule='unchanged published signed location correction, including temporal and satellite-disjoint TLE-history qualification',
        only_path_adapter_changed=True,observations_candidates_labels_masks_and_noise_unchanged=True,
        exact_original_fallback_when_unqualified_or_paired_gates_fail=True,
        cold_start_km=[0,0],box_width_km=25,phase_rounds=5,position_iterations=48,
        matched_c0_fitted_c=True,no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True,
        original_signed_evidence_audit_sha256=sha(SIGNED/'evaluation_audit.json'),
        prior_recovery_verification_sha256=sha(RECOVERY/'independent_recovery_evaluation.json'),
        existing_published_benchmarks_not_modified=True)
    write(path,protocol);return protocol


def job(case):
    import probe_ds23_causal_phase_location as engine

    protocol=read(OUT/'protocol.json');binding=protocol['recovered_original_bindings'][case]
    root=ROOT/binding['root']
    if sha(root/case/'algo02_result.json')!=binding['original_result_sha256'] or sha(root/case/'result.json')!=binding['initial_result_sha256']:
        raise ValueError('original recovered scientific fit changed')
    def context(selected_case):
        if selected_case!=case:raise ValueError('worker attempted to load another scan')
        bind_run_directory(root)
        scan=load_scan(root,case)
        original=read(root/case/'result.json');old=read(root/case/'algo02_result.json')
        node=original['final_node'];mask=np.asarray(old['mask'],bool)
        return scan,node,mask,problem(scan,node,'c0',mask),old
    engine.context=context
    engine.SOURCE=root
    return engine.run_case(case,str(OUT))


if __name__=='__main__':
    protocol=prepare();receipts=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(job,case):case for case in protocol['cases']}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
            write(OUT/'progress.json',dict(receipts=receipts,total=6))
    write(OUT/'execution.json',dict(all_terminal=True,receipts=receipts,errors=[r for r in receipts if 'error' in r]))
