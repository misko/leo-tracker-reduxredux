"""Frozen-model extension: one deterministic randomly ranked scan per sample rate."""
import argparse,hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXCLUDED={'scan-fw-4b863c775f5972ce','scan-fw-3228d496423f0b3d','scan-fw-fadea8b51ac3a4f7',
          'scan-fw-d86e8f23c0624bac','scan-fw-dc1153010e57ac76'}
SEED='joint-additional-v1-20260926:'


def select(scans):
    result=[]
    for rate in (2500000,5000000,7500000,10000000):
        eligible=[s for s in scans if s['sample_rate_hz']==rate and s['session_id'] not in EXCLUDED]
        chosen=min(eligible,key=lambda s:hashlib.sha256((SEED+s['session_id']).encode()).hexdigest())
        result.append({k:chosen[k] for k in ('session_id','capture_start_utc','sample_rate_hz','track_count')})
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,choices=(0,1));parser.add_argument('--select-only',action='store_true')
    args=parser.parse_args()
    source=HERE.parent/'2026_09_26_ds5_probabilistic/results.json'
    original=json.loads((HERE/'results.json').read_text())
    cal=HERE.parent/'2026_09_26_ds5_empirical_prior/calibration.json'
    assert hashlib.sha256((HERE/'core.py').read_bytes()).hexdigest()==original['core_sha256']
    assert hashlib.sha256(cal.read_bytes()).hexdigest()==original['calibration_sha256']
    chosen=select(json.loads(source.read_text())['scans'])
    receipt={'selection':'Lowest SHA256(seed+session_id) within each sample-rate stratum; no model scores used',
        'seed':SEED,'excluded':sorted(EXCLUDED),'selected':chosen,'core_sha256':original['core_sha256'],
        'calibration_sha256':original['calibration_sha256'],'original_results_sha256':hashlib.sha256((HERE/'results.json').read_bytes()).hexdigest()}
    path=HERE/'additional_selection.json'
    if path.exists():assert json.loads(path.read_text())==receipt
    else:path.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2),flush=True)
    if args.select_only:return
    assert args.shard is not None
    import run
    run.main([s['session_id'] for i,s in enumerate(chosen) if i%2==args.shard],HERE/f'additional_shard_{args.shard}.json')


if __name__=='__main__':main()
