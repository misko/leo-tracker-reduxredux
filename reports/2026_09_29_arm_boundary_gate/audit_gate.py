#!/usr/bin/env python3
"""Audit native boundary-gate cohorts with the frozen standard matcher."""
import argparse,json,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import independent_summary as frozen

def audit(folder,threshold):
    manifest=json.loads((folder/'manifest.json').read_text());assert manifest['complete']
    assert frozen.sha256(folder/'rows.jsonl')==manifest['rows_sha256']
    baseline_path=HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
    baseline=frozen.load_baseline(baseline_path);native=frozen.load_native(folder/'rows.jsonl')
    for windows in native.values():
        for row in windows.values():
            for candidate in row['candidates']:candidate['epoch']=candidate['refined_epoch']
    result=frozen.summarize(manifest['selected'],baseline,native)
    for group in [result['totals'],*result['by_rate'].values()]:
        group['unmatched_positive_hits']=group['native_positive_hits']-group['recovered_positive_hits']
        group['hit_recovery_fraction']=group['recovered_positive_hits']/group['reference_positive_hits'] if group['reference_positive_hits'] else None
    result.update(baseline_sha256=frozen.sha256(baseline_path),native_sha256=frozen.sha256(folder/'rows.jsonl'),manifest_sha256=frozen.sha256(folder/'manifest.json'),matcher_sha256=frozen.sha256(Path(frozen.__file__)),gate={'minimum_initial_margin':threshold,'native_condition':'boundary residual and finite margin below threshold skip refinement'})
    (folder/'standard-audit.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--threshold',type=float,required=True);a=p.parse_args()
    print(json.dumps(audit(a.cohort,a.threshold)['totals'],indent=2))
