"""Bounded retrospective ALGO07 replay; saved research authority, never publication."""
import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants')
CASES = ['DS26-0034','DS26-0251','DS26-0203','DS26-0070','DS26-0072','DS26-0221','DS26-0044','DS26-0100','DS26-0014','DS26-0201','DS26-0309','DS26-0209']
LIMIT = 1200


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    from algo07_science.validation import clean
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(value), indent=2, allow_nan=False)+'\n')


def report_endpoint(row):
    """Compute error only after selection; the runtime never receives truth."""
    import math
    from prototype_dsx01_continuous_position import latlon
    out=copy.deepcopy(row)
    lat,lon=latlon(row['x']);a,b=map(math.radians,[lat,37.849061591561885])
    term=math.sin((a-b)/2)**2+math.cos(a)*math.cos(b)*math.sin(math.radians(lon+122.48574968092912)/2)**2
    out['error_m']=6371000*2*math.asin(min(1,math.sqrt(term)))
    out['endpoint_latlon']=[lat,lon]
    return out


def prepare(case):
    from algo07_science import runner
    root = HERE/case
    if root.exists():
        raise FileExistsError(f'Fresh inputs required: {root}')
    inp = root/'input'
    sources = {}
    for relative, target in [('inputs/'+case+'.json', 'inputs/SCAN.json'),
                             ('catalogues/'+case+'.json', 'catalogues/SCAN.json'),
                             ('position/'+case+'/result.json', 'position/SCAN/result.json'),
                             ('screen/'+case+'/result.json', 'screen/SCAN/result.json')]:
        source, dest = SOURCE/relative, inp/target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        sources[str(source)] = sha(source)
    z = read(inp/'inputs/SCAN.json')
    z['case'] = 'SCAN'
    write(inp/'inputs/SCAN.json', z)
    expected = copy.deepcopy(z['baseline_owners'])
    published = read(inp/'position/SCAN/result.json')
    decision = published['decisions']['72h_30s']
    if decision['status'] == 'qualified':
        trial = published['trials'][decision['trial']]
        for arm in runner.e.ARMS:
            for oid in trial['entry']['observation_ids']:
                if oid in expected[arm]:
                    raise ValueError('Saved ALGO06 owner collision')
                expected[arm][oid] = trial['entry']['norad']
    write(inp/'saved-authority.json', dict(expected_owners=expected))
    write(inp/'exports/SCAN/published-algo06.json', dict(research_only=True, public_terminal_available=False))
    baseline = runner.published_baseline(inp, 'SCAN')
    # Hash frozen source inventory and directly referenced native inputs.
    for key in ('inventory_path',):
        path = Path(z[key]); sources[str(path)] = sha(path)
    native = Path(z['native_path'])
    for path in sorted(native.rglob('*')):
        if path.is_file() and path.suffix in ('.json','.tle','.npz','.npy'):
            sources[str(path)] = sha(path)
    write(root/'preparation.json', dict(source_case=case, source_sha256=sources,
          native_path=str(native), scan_cutoff_utc_ns=z['scan_receipt']['cutoff_utc_ns'],
          research_only=True, public_terminal_available=False))


def export_all():
    from algo07_history import export_history
    from leo.operations.tle_archive import TleArchiveReader
    reader = TleArchiveReader(Path('/var/lib/leo/tle'))
    for case in CASES:
        root = HERE/case
        z = read(root/'input/inputs/SCAN.json')
        path = root/'input/history-bank.json'
        if path.exists():
            raise FileExistsError('Fresh full history export required: '+str(path))
        began = time.monotonic()
        value = export_history(path, z['scan_receipt']['cutoff_utc_ns'], reader=reader)
        os.chmod(path, 0o644)
        write(root/'history-export.json', dict(path=str(path), sha256=sha(path),
              cutoff_utc_ns=value['cutoff_utc_ns'], snapshot_count=value['snapshot_count'],
              satellite_count=len(value['versions']),
              version_count=sum(map(len,value['versions'].values())),
              seconds=time.monotonic()-began,
              scope='All causal archive satellite versions; unrestricted candidate requests'))
        print(case, 'history exported', flush=True)


def worker(case):
    import numpy as np
    from algo07_science import runner
    root = HERE/case; inp = root/'input'; out = root/'output'
    protocol = read(out/'protocol.json'); baseline = protocol['baselines']['SCAN']
    expected = read(inp/'saved-authority.json')['expected_owners']
    def research_preflight(d,z,actual_baseline,terminal):
        assert terminal == dict(research_only=True, public_terminal_available=False)
        for arm,(problem, point) in d['problems'].items():
            np.testing.assert_array_equal(point, baseline[arm]['x'])
            if abs(runner.e.objective(problem,d,point)-baseline[arm]['objective'])>1e-4:
                raise ValueError('Saved research ALGO06 objective mismatch')
            if z['baseline_owners'][arm]!=expected[arm]:
                raise ValueError('Saved research ALGO06 owner mismatch')
        return dict(research_only=True,public_terminal_available=False,
                    saved_research_owner_maps_equal=True,saved_research_objectives_equal=True)
    runner.preflight_public = research_preflight
    runner.run_worker('SCAN', inp, out)


def supervise(case, code_sha):
    from algo07_science import runner
    root = HERE/case; inp = root/'input'; out = root/'output'
    if out.exists():
        raise FileExistsError('Fresh output required: '+str(out))
    baseline = runner.published_baseline(inp, 'SCAN')
    input_sha = {str(p.relative_to(inp)):sha(p) for p in sorted(inp.rglob('*')) if p.is_file()}
    write(out/'protocol.json', dict(baselines={'SCAN':baseline}, source_case=case,
          research_only=True, public_terminal_available=False, source_sha256=code_sha,
          input_sha256=input_sha,time_limit_s=LIMIT,numerical_settings=runner.SETTINGS,
          arms=list(runner.e.ARMS),evaluation_coordinate_role='postfit error reporting only'))
    command = [sys.executable,'-B',str(Path(__file__).resolve()),'--worker',case]
    write(root/'launch.json', dict(command=command,cwd=str(REPO),maximum_seconds=LIMIT,
          env={k:os.environ.get(k) for k in ('PYTHONPATH','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
          started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    began = time.monotonic(); failure = None; code = None
    with (root/'worker.log').open('xb') as stream:
        child = subprocess.Popen(command,cwd=REPO,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code = child.wait(timeout=LIMIT)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(child.pid,signal.SIGTERM)
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL);child.wait()
            failure = 'hardcap_fallback'
    if code != 0 and failure is None:
        failure = 'worker_failure_fallback'
    path = out/'SCAN/worker_result.json'
    result = read(path) if path.exists() and failure is None else runner.fallback(baseline,failure or 'missing_result_fallback')
    if failure:
        write(root/'supervisor_fallback.json',result)
    screens=[]
    for screen_path in sorted((out/'SCAN').glob('*/screen.json')):
        screen=read(screen_path); proposals=[]
        for h in screen.get('proposals',[]):
            reasons=[]
            if 'prediction_limit' in h: reasons.append('prediction_limit')
            if set(map(int,h.get('mapping',{}).values()))!={int(h['norad'])}: reasons.append('non_whole_family_mapping')
            if not all(h['predictive'][a]['pass_check'] for a in runner.e.ARMS): reasons.append('inherited_predictive_rejected')
            guard=result.get('guards',{}).get(h['name'])
            if guard and not guard.get('passed'): reasons.append('receiver_shared_guard_rejected:'+str(guard.get('reason',guard.get('status'))))
            proposals.append(dict(name=h['name'],norad=h['norad'],predictive=h['predictive'],guard=guard,
                rejection_reasons=reasons,admitted=not reasons and guard is not None and guard.get('passed',False)))
        screens.append(dict(target=int(screen_path.parent.name),status=screen.get('status','complete'),
            nominees=screen.get('nominees'),coarse=screen.get('coarse'),proposals=proposals))
    trigger=read(out/'SCAN/trigger.json') if (out/'SCAN/trigger.json').exists() else None
    summary = dict(source_case=case,private_label='SCAN',research_only=True,public_terminal_available=False,
          execution_status=result['execution_status'],selected=result['selected'],
          baseline={a:report_endpoint(r) for a,r in baseline.items()},
          final={a:report_endpoint(r) for a,r in result['final'].items()},
          guards=result.get('guards',{}),targets=result.get('targets',[]),trigger=trigger,screens=screens,
          candidate_records=[dict(name=r['name'],accepted=r['accepted'],gains=r.get('gains'),bounds=r.get('bounds'),
              pairs={a:({k:v for k,v in report_endpoint(p).items() if k in ('x','endpoint_latlon','error_m','objective','active_points','qualified','rms_hz')}
                    if p else None) for a,p in r.get('pair',{}).items()}) for r in result.get('records',[])],
          subprocess_returncode=child.returncode,supervisor_failure=failure,seconds=time.monotonic()-began,
          exact_fallback_equal=result['final']==baseline if result['selected'] is None else None,
          output_protocol_sha256=sha(out/'protocol.json'))
    write(root/'summary.json',summary)
    print(case,result['execution_status'],result['selected'],round(summary['seconds'],1),flush=True)
    return summary


def main():
    global CASES
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--export',action='store_true')
    p.add_argument('--worker');p.add_argument('--run',action='store_true');p.add_argument('--cases',nargs='+');a=p.parse_args()
    if a.cases: CASES=a.cases
    if a.prepare:
        for case in CASES: prepare(case)
    elif a.export: export_all()
    elif a.worker: worker(a.worker)
    elif a.run:
        from algo07_production_worker import verify_release
        verify_release()
        names=subprocess.check_output(['git','ls-files','src','tools'],cwd=REPO,text=True).splitlines()
        code_sha={name:sha(REPO/name) for name in names if (REPO/name).is_file()}
        code_sha[str(Path(__file__).resolve())]=sha(Path(__file__).resolve())
        write(HERE/'code-freeze.json',dict(sha256=code_sha,
              git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              algorithm='deployed ALGO07',cases=CASES,maximum_seconds=LIMIT,workers=6,
              gps_for_error_reporting_only=[37.849061591561885,-122.48574968092912]))
        results=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            jobs={pool.submit(supervise,case,code_sha):case for case in CASES}
            for future in concurrent.futures.as_completed(jobs):
                try: results.append(future.result())
                except Exception as exc:
                    row=dict(source_case=jobs[future],execution_status='supervisor_failure',reason=repr(exc),traceback=traceback.format_exc())
                    write(HERE/jobs[future]/'summary.json',row);results.append(row)
                write(HERE/'summary.json',sorted(results,key=lambda r:CASES.index(r['source_case'])))
        verify_release()
        if any(sha(REPO/name)!=expected for name,expected in code_sha.items() if not name.startswith('/')):
            raise ValueError('Frozen scientific code changed during evaluation')
        import csv
        with (HERE/'summary.csv').open('w',newline='') as stream:
            fields=['case','execution_status','selected','seconds','exact_fallback_equal','arm','before_error_m','after_error_m','before_associated','after_associated','before_objective','after_objective']
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for row in sorted(results,key=lambda r:CASES.index(r['source_case'])):
                for arm,before in row.get('baseline',{}).items():
                    after=row['final'][arm]
                    writer.writerow(dict(case=row['source_case'],execution_status=row['execution_status'],selected=row['selected'],
                        seconds=row['seconds'],exact_fallback_equal=row['exact_fallback_equal'],arm=arm,
                        before_error_m=before['error_m'],after_error_m=after['error_m'],before_associated=before['associated'],
                        after_associated=after['associated'],before_objective=before['objective'],after_objective=after['objective']))
    else: p.error('Choose one mode')


if __name__=='__main__':
    main()
