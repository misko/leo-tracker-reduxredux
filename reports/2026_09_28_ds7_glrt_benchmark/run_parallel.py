"""Four-core exact-workload arm; run only after serial timing completes."""
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
from methods_parallel import make_parallel_method, ADAPTER_PATH, CORES
from run import validate_inputs, sha, HERE, REPO


def timeout(_signum,_frame):
    raise TimeoutError('parallel replay deadline')


def run():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--plan',type=Path,default=HERE/'plan.json');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();plan=json.loads(a.plan.read_text())
    inputs=json.loads((a.inputs/'inputs.json').read_text());validate_inputs(plan,inputs,a.plan)
    a.output.mkdir(parents=True,exist_ok=False)
    os.sched_setaffinity(0,set(CORES));signal.signal(signal.SIGALRM,timeout);signal.alarm(900)
    deps=[Path(__file__),HERE/'methods_parallel.py',HERE/'methods.py',ADAPTER_PATH,
          REPO/'src/leo/scanner/detector.py',REPO/'src/leo/scanner/models.py',
          REPO/'src/leo/analysis/starlink/acquisition.py',REPO/'src/leo/analysis/starlink/pilot_methods.py']
    hashes={str(p):sha(p) for p in deps}
    header={'schema':'ds7-glrt-run/v1','plan_sha256':sha(a.plan),
        'input_manifest_sha256':sha(a.inputs/'inputs.json'),'dataset_sha256':plan['dataset_sha256'],
        'source_hashes':hashes,'methods':['parallel4'],'repetitions':plan['repetitions'],
        'scope':'same complete detector; four persistent workers, numerical threads 1, aggregate parent+worker CPU',
        'python':sys.version,'platform':platform.platform(),'cores':list(CORES),
        'complete':False,'sources_unchanged':False,'failed_calls':0,
        'planned_calls':len(inputs['rows'])*plan['repetitions']}
    (a.output/'run.json').write_text(json.dumps(header,indent=2)+'\n')
    method=None;calls=0;started=time.monotonic()
    try:
        method=make_parallel_method();header['creation']=method.creation_diagnostics
        os.sched_setaffinity(0,{0})
        with (a.output/'rows.jsonl').open('x') as output:
            for repeat in range(plan['repetitions']):
                method.reset()
                for context in inputs['rows']:
                    path=a.inputs/context['file']
                    if path.parent.resolve()!=a.inputs.resolve() or sha(path)!=context['sha256']:
                        raise ValueError('payload binding')
                    iq=np.load(path,allow_pickle=False);rate=context['rate_hz']
                    if list(iq.shape)!=context['shape'] or str(iq.dtype)!=context['dtype']:
                        raise ValueError('input geometry')
                    duration=iq.shape[0]*1000/rate
                    if duration!=int(duration):raise ValueError('dwell geometry')
                    config=ScannerConfiguration(sample_rate_hz=rate,bandwidth_hz=rate,dwell_ms=int(duration),
                        targets=(ScanTarget.model_validate(context['target']),))
                    cpu=time.process_time();wall=time.perf_counter()
                    samples=np.empty(iq.shape[:2],dtype=np.complex64)
                    samples.real=iq[:,:,0];samples.imag=iq[:,:,1]
                    got=method.analyze(samples,config,context['target']['edge'],context)
                    timing={'cpu_s':time.process_time()-cpu+got.diagnostics['worker_cpu_s'],
                            'wall_s':time.perf_counter()-wall}
                    result=TypeAdapter(type(got.analysis)).dump_python(got.analysis,mode='json')
                    output.write(json.dumps({'context':context,'method':'parallel4','repeat':repeat,
                        'status':'ok','result':result,'diagnostics':got.diagnostics,'timing':timing},allow_nan=False)+'\n')
                    output.flush();calls+=1
                    print(json.dumps({'repeat':repeat,'rate':rate,'visit':context['visit_index'],'calls':calls}),flush=True)
        method.close();header['workers_closed']=True
        header['sources_unchanged']=all(sha(Path(p))==h for p,h in hashes.items())
        header['complete']=calls==header['planned_calls'] and header['sources_unchanged']
    except BaseException as e:
        header['error']=repr(e);header['failed_calls']=1
        if method is not None:method.abort();header['workers_aborted']=True
        raise
    finally:
        signal.alarm(0)
        header.update(calls=calls,wall_s=time.monotonic()-started,
                      parent_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        (a.output/'run.json').write_text(json.dumps(header,indent=2)+'\n')


if __name__=='__main__':run()
