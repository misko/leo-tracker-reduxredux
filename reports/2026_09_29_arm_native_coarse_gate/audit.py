#!/usr/bin/env python3
"""Frozen standard audit permitting the coarse gate's smaller inventories."""
import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import independent_summary as frozen
def load_gated(path):
 result={}
 for line in path.read_text().splitlines():
  record=json.loads(line);case=(record['context']['session_id'],record['context']['visit_index']);assert record['returncode']==0 and not record['stderr'] and len(record['rows'])==22 and case not in result;windows={}
  for row in record['rows']:
   key=(row['receiver_id'],row['probe_index']);assert key not in windows and row['candidate_count']==len(row['candidates']) and 0<=row['candidate_count']<=8;windows[key]=row
   for candidate in row['candidates']:candidate['epoch']=candidate['refined_epoch']
  assert set(windows)==frozen.WINDOW_KEYS;result[case]=windows
 return result
def annotate_candidate_inventories(result,manifest,native):
    """Keep the frozen matcher's baseline inventory distinct from emitted rows."""
    rates={(item['session_id'],item['visit_index']):str(item['rate_hz']) for item in manifest['selected']}
    emitted={'total':0}
    for case,windows in native.items():
        rate=rates[case];emitted[rate]=emitted.get(rate,0)+sum(row['candidate_count'] for row in windows.values())
        emitted['total']+=sum(row['candidate_count'] for row in windows.values())
    for rate,group in result['by_rate'].items():
        group['reference_candidate_entries']=group['candidates']
        group['emitted_candidate_entries']=emitted.get(rate,0)
        group['candidates_meaning']='frozen reference inventory'
    result['totals']['reference_candidate_entries']=result['totals']['candidates']
    result['totals']['emitted_candidate_entries']=emitted['total']
    result['totals']['candidates_meaning']='frozen reference inventory'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--cohort',type=Path,default=HERE/'host704');args=parser.parse_args()
 folder=args.cohort;manifest=json.loads((folder/'manifest.json').read_text());assert manifest['complete'];assert frozen.sha256(folder/'rows.jsonl')==manifest['rows_sha256']
 baseline_path=HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl';native=load_gated(folder/'rows.jsonl');result=frozen.summarize(manifest['selected'],frozen.load_baseline(baseline_path),native);annotate_candidate_inventories(result,manifest,native)
 for group in [result['totals'],*result['by_rate'].values()]:
  group['unmatched_positive_hits']=group['native_positive_hits']-group['recovered_positive_hits'];group['hit_recovery_fraction']=group['recovered_positive_hits']/group['reference_positive_hits']
 result.update(baseline_sha256=frozen.sha256(baseline_path),native_sha256=frozen.sha256(folder/'rows.jsonl'),manifest_sha256=frozen.sha256(folder/'manifest.json'),matcher_sha256=frozen.sha256(Path(frozen.__file__)),coarse_score_gate=.15)
 (folder/'standard-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['totals'],indent=2))
if __name__=='__main__':main()
