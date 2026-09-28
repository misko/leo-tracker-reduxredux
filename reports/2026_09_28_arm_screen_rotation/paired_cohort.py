"""Compare a completed cohort with the preceding qualified CZT candidate objects."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,default=Path('reports/2026_09_28_arm_conditioned_czt/host704-v2'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    def load(folder):
        manifest=json.loads((folder/'manifest.json').read_text());assert manifest['complete']
        records=[json.loads(s) for s in (folder/'rows.jsonl').read_text().splitlines()]
        rows={r['context']['ordinal']:r for r in records};assert len(rows)==len(records)==manifest['processed_dwells']
        return rows
    ref,got=load(args.baseline),load(args.candidate)
    windows=objects=hits=positive=0
    for ordinal,row in got.items():
        old=ref[ordinal];assert row['context']['sha256']==old['context']['sha256']
        assert row['returncode']==old['returncode']==0
        a={(r['receiver_id'],r['probe_index']):r for r in row['rows']}
        b={(r['receiver_id'],r['probe_index']):r for r in old['rows']}
        assert len(a)==len(row['rows'])==len(b)==22 and a.keys()==b.keys()
        for key in a:
            assert a[key]['candidates']==b[key]['candidates'],(ordinal,key)
            n=sum(c['margin']>=.025 for c in b[key]['candidates'])
            windows+=1;objects+=len(a[key]['candidates']);hits+=n;positive+=n>0
    result=dict(dwells=len(got),windows=windows,candidate_objects=objects,all_candidates_identical=True,baseline_hits=hits,recovered_hits=hits,baseline_positive_windows=positive,recovered_positive_windows=positive,added_hits=0,baseline_rows_sha256=hashlib.sha256((args.baseline/'rows.jsonl').read_bytes()).hexdigest(),candidate_rows_sha256=hashlib.sha256((args.candidate/'rows.jsonl').read_bytes()).hexdigest())
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
