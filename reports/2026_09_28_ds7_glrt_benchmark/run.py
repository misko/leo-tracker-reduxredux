"""Bounded causal, counterbalanced GLRT method replay on frozen local DS7 extracts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import time

import numpy as np
from pydantic import TypeAdapter
from leo.scanner.models import ScannerConfiguration, ScanTarget
from leo.analysis.starlink.acquisition import _folded_anchor_score_grid_backend

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_inputs(plan, receipt, plan_path):
    if not receipt.get('complete') or receipt['plan_sha256']!=sha(plan_path):
        raise ValueError('input/plan binding')
    if receipt['dataset_sha256']!=plan['dataset_sha256']:
        raise ValueError('dataset identity')
    expected=[(c['session_id'],v,c['sample_rate_hz'],c['manifest_sha256'])
              for c in plan['captures'] for v in c['visit_indices']]
    actual=[(r['session_id'],r['visit_index'],r['rate_hz'],r['manifest_sha256']) for r in receipt['rows']]
    if expected!=actual or len(set(actual))!=len(actual):
        raise ValueError('cohort membership/order')
    if receipt['iq_bytes']>plan['maximum_uncompressed_iq_bytes']:
        raise ValueError('IQ budget')


def run():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--plan',type=Path,default=HERE/'plan.json')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--methods',nargs='+')
    args=p.parse_args()
    from methods import make_method
    plan=json.loads(args.plan.read_text());inputs=json.loads((args.inputs/'inputs.json').read_text())
    validate_inputs(plan,inputs,args.plan)
    selected=args.methods or plan['methods']
    if not selected or len(set(selected))!=len(selected) or any(n not in plan['methods'] for n in selected):
        raise ValueError('method allowlist')
    os.sched_setaffinity(0,{plan['cpu_core']})
    signal.alarm(plan['runner_wall_limit_s'])
    args.output.mkdir(parents=True,exist_ok=False)
    deps=[HERE/'methods.py',Path(__file__),REPO/'src/leo/scanner/detector.py',
          REPO/'src/leo/scanner/models.py',REPO/'src/leo/analysis/starlink/acquisition.py',
          REPO/'src/leo/analysis/starlink/pilot_methods.py',
          REPO/'reports/2026_09_27_server_scan_speed/pilot_methods_baseline.py',
          REPO/'reports/2026_09_27_server_scan_speed/acquisition_peak/original/acquisition.py']
    hashes={str(f):sha(f) for f in deps}
    header={'schema':'ds7-glrt-run/v1','plan_sha256':sha(args.plan),
            'input_manifest_sha256':sha(args.inputs/'inputs.json'),
            'dataset_sha256':plan['dataset_sha256'],'source_hashes':hashes,
            'methods':selected,'repetitions':plan['repetitions'],
            'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,
            'backend':_folded_anchor_score_grid_backend(),'affinity':sorted(os.sched_getaffinity(0)),
            'threads':{k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')},
            'scope':'resident CI16 conversion plus full detector; storage/serialization outside per-call timing; no RF',
            'complete':False,'planned_calls':len(inputs['rows'])*len(selected)*plan['repetitions']}
    (args.output/'run.json').write_text(json.dumps(header,indent=2)+'\n')
    started=time.monotonic();calls=0;failures=0;construction_cpu=0
    with (args.output/'rows.jsonl').open('x') as output:
        for repeat in range(plan['repetitions']):
            cpu=time.process_time();workers={n:make_method(n) for n in selected}
            construction_cpu+=time.process_time()-cpu
            for ordinal,context in enumerate(inputs['rows']):
                path=args.inputs/context['file']
                if path.parent.resolve()!=args.inputs.resolve() or sha(path)!=context['sha256']:
                    raise ValueError('input payload binding')
                iq=np.load(path,allow_pickle=False)
                if list(iq.shape)!=context['shape'] or str(iq.dtype)!=context['dtype']:
                    raise ValueError('input geometry')
                rate=context['rate_hz'];duration=iq.shape[0]*1000/rate
                if duration!=int(duration):raise ValueError('nonintegral dwell')
                config=ScannerConfiguration(sample_rate_hz=rate,bandwidth_hz=rate,
                    dwell_ms=int(duration),targets=(ScanTarget.model_validate(context['target']),))
                shift=(ordinal+repeat)%len(selected);order=selected[shift:]+selected[:shift]
                for name in order:
                    cpu=time.process_time();wall=time.perf_counter()
                    try:
                        samples=np.empty(iq.shape[:2],dtype=np.complex64)
                        samples.real=iq[:,:,0];samples.imag=iq[:,:,1]
                        got=workers[name].analyze(samples,config,context['target']['edge'],context)
                        timing={'cpu_s':time.process_time()-cpu,'wall_s':time.perf_counter()-wall}
                        result=TypeAdapter(type(got.analysis)).dump_python(got.analysis,mode='json')
                        row={'context':context,'method':name,'repeat':repeat,'status':'ok',
                             'result':result,'diagnostics':got.diagnostics,'timing':timing}
                    except Exception as e:
                        row={'context':context,'method':name,'repeat':repeat,'status':'failed',
                             'result':None,'diagnostics':{'error':repr(e)},
                             'timing':{'cpu_s':time.process_time()-cpu,'wall_s':time.perf_counter()-wall}}
                        failures+=1
                    output.write(json.dumps(row,allow_nan=False)+'\n');output.flush();calls+=1
                print(json.dumps({'repeat':repeat,'rate':rate,'visit':context['visit_index'],
                                  'calls':calls,'failures':failures}),flush=True)
    stable=all(sha(Path(f))==h for f,h in hashes.items())
    header.update(complete=calls==header['planned_calls'],calls=calls,failed_calls=failures,
                  sources_unchanged=stable,wall_s=time.monotonic()-started,
                  constructor_cpu_s=construction_cpu,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    (args.output/'run.json').write_text(json.dumps(header,indent=2)+'\n')
    if failures or not stable:raise RuntimeError('invalid/failed run; rows retained')


if __name__=='__main__':run()
