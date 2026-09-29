#!/usr/bin/env python3
"""Run the frozen standard matcher for a fixed eight-candidate cohort."""
import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import independent_summary as frozen

def load_native(path):
    result={}
    for line in path.read_text().splitlines():
        record=json.loads(line); context=record['context']; key=(context['session_id'],context['visit_index'])
        assert record['returncode']==0 and not record['stderr'] and len(record['rows'])==22 and key not in result
        windows={}
        for row in record['rows']:
            window=(row['receiver_id'],row['probe_index'])
            assert window not in windows and row['candidate_count']==len(row['candidates'])==8
            for candidate in row['candidates']: candidate['epoch']=candidate['refined_epoch']
            windows[window]=row
        assert set(windows)==frozen.WINDOW_KEYS; result[key]=windows
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',type=Path,default=HERE/'host704');args=parser.parse_args()
    folder=args.cohort;manifest=json.loads((folder/'manifest.json').read_text());assert manifest['complete']
    assert frozen.sha256(folder/'rows.jsonl')==manifest['rows_sha256']
    baseline=HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
    result=frozen.summarize(manifest['selected'],frozen.load_baseline(baseline),load_native(folder/'rows.jsonl'))
    for group in [result['totals'],*result['by_rate'].values()]:
        group['unmatched_positive_hits']=group['native_positive_hits']-group['recovered_positive_hits']
        group['hit_recovery_fraction']=group['recovered_positive_hits']/group['reference_positive_hits']
    result.update(baseline_sha256=frozen.sha256(baseline),native_sha256=frozen.sha256(folder/'rows.jsonl'),manifest_sha256=frozen.sha256(folder/'manifest.json'),matcher_sha256=frozen.sha256(Path(frozen.__file__)))
    (folder/'standard-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['totals'],indent=2))
if __name__=='__main__': main()
