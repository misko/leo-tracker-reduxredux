"""Freeze metadata-only DS7 selection, then extract through the public read-only port."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO/'tools'))
import ds7_eval


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan(output):
    manifest, _ = ds7_eval.load_dataset()
    captures = []
    for rate, count in ((2500000, 16), (5000000, 4), (7500000, 4), (10000000, 4)):
        c = next(c for c in manifest['captures'] if c['sample_rate_hz'] == rate)
        start = c['visits']//2
        captures.append({k: c[k] for k in ('session_id','manifest_sha256','sample_rate_hz','receiver_ids')} |
                        {'visit_indices': list(range(start, start+count))})
    document = {'schema': 'ds7-glrt-plan/v1', 'dataset_sha256': ds7_eval.DS7_SHA256,
        'selection': 'first chronological recording per native rate; consecutive midpoint visits; no detector outcome used',
        'scope': 'exposed development smoke cohort, not independent holdout or whole DS7',
        'captures': captures, 'maximum_uncompressed_iq_bytes': 512*1024*1024,
        'methods': ['original','optimized','candidates2','local_fallback'],
        'repetitions': 2, 'cpu_core': 0, 'runner_wall_limit_s': 1800,
        'candidate_margin_gate': .025, 'identity_timing_tolerance_us': 2.,
        'identity_cfo_tolerance_hz': 8000., 'tracking_max_age_s': 3.,
        'local_cfo_radius_hz': 20000., 'full_blind_fallback': True}
    with output.open('x') as f:
        json.dump(document,f,indent=2);f.write('\n')
    print(output)


def extract(plan_path, output):
    import numpy as np
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    signal.alarm(300)
    spec = json.loads(plan_path.read_text())
    manifest, _ = ds7_eval.load_dataset()
    allowed = {c['session_id']: c for c in manifest['captures']}
    if spec['dataset_sha256'] != ds7_eval.DS7_SHA256:
        raise ValueError('dataset binding')
    output.mkdir(parents=True, exist_ok=False)
    rows = []; total = 0
    store = AdaptiveHopIqStore('/srv/bulk/leo', read_only=True)
    try:
        for capture in spec['captures']:
            published = ds7_eval.load_recording(allowed[capture['session_id']], store)
            if published.manifest_sha256 != capture['manifest_sha256']:
                raise ValueError('source binding')
            reader = store.reader(capture['session_id'], expected=published)
            try:
                for index in capture['visit_indices']:
                    started = time.perf_counter(); visit, iq = reader.read_visit_ci16(index)
                    read_wall = time.perf_counter()-started
                    total += iq.nbytes
                    if total > spec['maximum_uncompressed_iq_bytes']:
                        raise ValueError('IQ budget exceeded')
                    event = visit.event
                    if event.visit_index != index or tuple(iq.shape[1:]) != (2,2):
                        raise ValueError('visit geometry')
                    filename = f'{capture["session_id"]}-{index}.npy'
                    np.save(output/filename, iq, allow_pickle=False)
                    rows.append({'session_id': capture['session_id'], 'visit_index': index,
                        'manifest_sha256': capture['manifest_sha256'],
                        'sample_start_counter': event.valid_start_counter,
                        'sample_end_counter': visit.valid_end_counter_exclusive,
                        'rate_hz': capture['sample_rate_hz'], 'target_index': event.target_index,
                        'target': event.target.model_dump(mode='json'),
                        'actual_lo_frequency_hz': event.actual_lo_frequency_hz,
                        'actual_if_offset_hz': event.actual_if_offset_hz,
                        'shape': list(iq.shape), 'dtype': str(iq.dtype), 'file': filename,
                        'sha256': sha(output/filename), 'iq_bytes': iq.nbytes,
                        'read_decode_wall_s': read_wall})
            finally:
                reader.close()
    finally:
        store.close()
    receipt = {'schema':'ds7-glrt-inputs/v1','plan_sha256':sha(plan_path),
        'dataset_sha256':spec['dataset_sha256'], 'complete':True, 'rows':rows,
        'iq_bytes':total, 'integrity':'source manifests verified; public reader checks selected chunk payloads; no full-corpus IQ hash claim'}
    with (output/'inputs.json').open('x') as f:
        json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'visits':len(rows),'iq_bytes':total,'output':str(output)}))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('plan','extract'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plan',type=Path)
    a=p.parse_args()
    if a.command=='plan':plan(a.output)
    else:extract(a.plan,a.output)
