"""Strict paired comparison of successive full-inventory ARM implementations."""
import argparse
import hashlib
import json
from pathlib import Path


def compare(baseline, candidate):
    def load(folder):
        assert json.loads((folder/'summary.json').read_text())['passed']
        rows = [json.loads(line) for line in (folder/'raw.jsonl').read_text().splitlines()]
        keyed = {(r['context']['ordinal'],r['native']['receiver_id'],r['native']['probe_index']):r for r in rows}
        assert len(keyed) == len(rows)
        return keyed
    reference, observed = load(baseline), load(candidate)
    assert reference.keys() == observed.keys()
    hits, positive_windows, identical = 0, 0, 0
    for key, ref in reference.items():
        got = observed[key]
        assert ref['context']['sha256'] == got['context']['sha256']
        a, b = ref['native']['candidates'], got['native']['candidates']
        if a == b:
            identical += 1
        count = sum(c['margin'] >= .025 for c in a)
        hits += count
        positive_windows += count > 0
    result = dict(windows=len(reference), candidate_objects=sum(len(r['native']['candidates']) for r in reference.values()), windows_with_identical_candidates=identical, all_candidates_identical=identical==len(reference), baseline_positive_windows=positive_windows, baseline_hits=hits, baseline_raw_sha256=hashlib.sha256((baseline/'raw.jsonl').read_bytes()).hexdigest(), candidate_raw_sha256=hashlib.sha256((candidate/'raw.jsonl').read_bytes()).hexdigest())
    if result['all_candidates_identical']:
        result.update(recovered_positive_windows=positive_windows,recovered_hits=hits,added_hits=0)
    summaries = [json.loads((p/'summary.json').read_text()) for p in (baseline,candidate)]
    result['cpu_ms_per_dwell'] = [r['timing_ms_per_dwell']['total_cpu'] for r in summaries]
    result['speedup'] = result['cpu_ms_per_dwell'][0]/result['cpu_ms_per_dwell'][1]
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=compare(args.baseline,args.candidate)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    assert result['all_candidates_identical']
