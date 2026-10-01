"""Time the unchanged rolling-backfill tracker on physical ARM, after detector replay."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_30_arm_streaming_tracks'))
from run_device import SSH,AUTH,OPTIONS,WRAPPER
REMOTE='/mnt/glrtbench/full-scan-f363-ungated-20261001'
BINARY='/mnt/glrtbench/streaming-tracks-f363-v1/rolling-backfill-cli'

def run(args):return subprocess.run(args,text=True,capture_output=True,check=True,timeout=120)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert json.loads((HERE/'arm/completion.json').read_text())['status']=='PASS'
    local=HERE/'analysis/observations.tsv'
    binary=HERE.parent/'2026_10_01_arm_rolling_backfill/component/leo-streaming-rolling-backfill-arm'
    assert run(SSH+[f'sha256sum {BINARY}']).stdout.split()[0]==sha(binary)
    run(AUTH+['scp','-O']+OPTIONS+[str(local),f'root@192.168.1.15:{REMOTE}/observations.tsv'])
    assert run(SSH+[f'sha256sum {REMOTE}/observations.tsv']).stdout.split()[0]==sha(local)
    out=HERE/'tracking-device';out.mkdir(exist_ok=False)
    trials=[]
    for i in range(3):
        result=run(SSH+[f'{WRAPPER} 90 {BINARY} {REMOTE}/observations.tsv'])
        (out/f'tracks-{i}.tsv').write_text(result.stdout);(out/f'tracks-{i}.stderr').write_text(result.stderr)
        assert sha(out/f'tracks-{i}.tsv')==sha(HERE/'analysis/tracks-0.tsv')
        timing=next(float(l.split('\t')[2]) for l in result.stderr.splitlines() if l.startswith('TIMING\treconstruct_s\t'))
        whole=next(json.loads(l) for l in result.stderr.splitlines() if l.startswith('{'))
        trials.append({'tracking_s':timing,'whole':whole,'host_byte_identical':True})
    receipt={'binary_sha256':sha(binary),'input_sha256':sha(local),'trials':trials,
        'median_tracking_s':statistics.median(t['tracking_s'] for t in trials),
        'median_whole_s':statistics.median(t['whole']['wall_s'] for t in trials)}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
