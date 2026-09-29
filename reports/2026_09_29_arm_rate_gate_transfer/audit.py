#!/usr/bin/env python3
"""Run the frozen positive-hit matcher on a 32-dwell transfer result."""
import argparse,hashlib,importlib.util,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
MATCHER=HERE.parent/'2026_09_28_arm_full_optimization/independent_summary.py'
BASELINE=HERE.parent/'2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_gated(path,window_keys):
    result={}
    for line in path.read_text().splitlines():
        record=json.loads(line);ctx=record['context'];case=(ctx['session_id'],ctx['visit_index'])
        if case in result or record['returncode']!=0 or record['stderr'] or len(record['rows'])!=22:
            raise ValueError(f'invalid gated execution: {case}')
        windows={}
        for row in record['rows']:
            key=(row['receiver_id'],row['probe_index'])
            if key in windows or row['candidate_count']!=len(row['candidates']) or not 0<=row['candidate_count']<=8:
                raise ValueError(f'invalid gated window: {case} {key}')
            windows[key]=row
        if set(windows)!=window_keys:raise ValueError(f'gated window inventory differs: {case}')
        result[case]=windows
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('frozen_matcher',MATCHER);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    manifest=json.loads((a.cohort/'manifest.json').read_text())
    if not manifest['complete'] or manifest['processed_dwells']!=32:raise ValueError('expected one complete 32-dwell transfer panel')
    native=load_gated(a.cohort/'rows.jsonl',m.WINDOW_KEYS)
    result=m.summarize(manifest['selected'],m.load_baseline(BASELINE),native)
    for counts in [result['totals'],*result['by_rate'].values()]:
        counts['unmatched_positive_hits']=counts['native_positive_hits']-counts['recovered_positive_hits']
        counts['hit_recovery_fraction']=counts['recovered_positive_hits']/counts['reference_positive_hits'] if counts['reference_positive_hits'] else 1.0
    result.update({'schema':'arm-rate-gate-transfer-audit/v1','baseline_sha256':sha(BASELINE),
        'native_sha256':sha(a.cohort/'rows.jsonl'),'manifest_sha256':sha(a.cohort/'manifest.json'),
        'matcher_sha256':sha(MATCHER),'gate':{'margin':m.MARGIN_GATE,'epoch_samples':m.EPOCH_TOLERANCE,
        'tracking_cfo_hz':m.HIT_CFO_TOLERANCE_HZ}})
    (a.cohort/'standard-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['totals'],indent=2))
if __name__=='__main__':main()
