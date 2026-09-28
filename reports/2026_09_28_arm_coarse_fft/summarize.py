"""Summarize completed ARM microbench receipts without implying GLRT speed."""
import hashlib
import json
from pathlib import Path


def main():
    folder=Path(__file__).resolve().parent
    runs={}
    for path in sorted(folder.glob('arm-microbench-v*/result.json')):
        r=json.loads(path.read_text());assert r['returncode']==0
        rows=[]
        for line in r['stdout'].splitlines():
            if not line.startswith('taps='):continue
            row={k:float(v) for k,v in (item.split('=') for item in line.split())}
            row['rate_hz']=int(row['taps']/4.4e-6+0.5)
            rows.append(row)
        assert len(rows)==12
        best=[]
        for taps in [11,22,33,44]:
            best.append(min((row for row in rows if row['taps']==taps),key=lambda row:row['fft_ms']))
        runs[path.parent.name]=dict(receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),rows=rows,best_by_taps=best)
    result=dict(scope='ARM CPU0 synthetic correlation-bank microbenchmark; not full GLRT timings or hit recovery. Setup excluded, median of three executions.',runs=runs)
    (folder/'benchmark_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    for name,r in runs.items():
        print(name,[(int(x['taps']),int(x['fft']),x['speedup']) for x in r['best_by_taps']])


if __name__=='__main__':main()
