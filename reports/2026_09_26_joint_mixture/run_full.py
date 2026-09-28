"""Resumable DS5 coverage, reusing seven verified completed cases."""
import argparse,concurrent.futures,hashlib,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_26_ds5_probabilistic/results.json'
EXISTING=('results.json','additional_shard_0.json','additional_shard_1.json')


def verify(payload,baseline):
    for key in ('source_sha256','core_sha256','calibration_sha256'):
        if payload[key]!=baseline[key]:raise ValueError(f'incompatible {key}')


def plan():
    baseline=json.loads((HERE/'results.json').read_text())
    for path,key in [(HERE/'core.py','core_sha256'),(SOURCE,'source_sha256'),
        (HERE.parent/'2026_09_26_ds5_empirical_prior/calibration.json','calibration_sha256')]:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==baseline[key]
    scans=json.loads(SOURCE.read_text())['scans'];expected={s['session_id'] for s in scans};completed={}
    for name in EXISTING:
        p=json.loads((HERE/name).read_text());verify(p,baseline)
        for s in p['scans']:
            assert s['session_id'] not in completed
            completed[s['session_id']]=name
    for path in sorted((HERE/'full_scans').glob('*.json')):
        p=json.loads(path.read_text());verify(p,baseline)
        assert len(p['scans'])==1
        s=p['scans'][0];assert path.stem==s['session_id'] and s['session_id'] not in completed
        completed[s['session_id']]=str(path.relative_to(HERE))
    assert set(completed)<=expected and len(expected)==42
    return scans,completed,baseline


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--session');parser.add_argument('--workers',type=int,default=8)
    args=parser.parse_args();scans,done,baseline=plan()
    (HERE/'full_scans').mkdir(exist_ok=True);(HERE/'full_logs').mkdir(exist_ok=True)
    if args.session:
        assert args.session in {s['session_id'] for s in scans}
        if args.session in done:return
        import run
        run.main([args.session],HERE/'full_scans'/f'{args.session}.json')
        return
    assert 1<=args.workers<=8
    todo=[s['session_id'] for s in scans if s['session_id'] not in done]
    receipt={'expected':42,'reused':done,'scheduled':todo,'workers':args.workers,
        'core_sha256':baseline['core_sha256'],'calibration_sha256':baseline['calibration_sha256'],
        'source_sha256':baseline['source_sha256'],'runner_sha256':hashlib.sha256((HERE/'run.py').read_bytes()).hexdigest()}
    (HERE/'full_run_plan.json').write_text(json.dumps(receipt,indent=2)+'\n')
    def execute(sid):
        started=time.monotonic()
        with (HERE/'full_logs'/f'{sid}.log').open('w') as log:
            r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--session',sid],stdout=log,stderr=subprocess.STDOUT)
        return {'session_id':sid,'returncode':r.returncode,'elapsed_s':time.monotonic()-started}
    progress=[]
    print('REUSED',len(done),'SCHEDULED',len(todo),'WORKERS',args.workers,flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(execute,sid) for sid in todo]):
            result=future.result();progress.append(result)
            tmp=HERE/'full_progress.json.tmp';tmp.write_text(json.dumps(progress,indent=2)+'\n');tmp.replace(HERE/'full_progress.json')
            print('COMPLETED',len(done)+sum(r['returncode']==0 for r in progress),'/42',result,flush=True)
    assert all(r['returncode']==0 for r in progress),'Failures recorded in full_progress.json and per-session logs'
    assert len(plan()[1])==42


if __name__=='__main__':main()
