"""External captured-call BLAS thread gate; no production or solver changes."""

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def library_info(paths=None, loader=ctypes.CDLL):
    """Read C API counters from both actually loaded wheel BLAS libraries."""
    if paths is None:
        lines = Path('/proc/self/maps').read_text().splitlines()
        paths = sorted({line.split()[-1] for line in lines
                        if 'openblas' in line.lower()})
    rows = []
    for path in paths:
        owner = ('numpy' if '/numpy.libs/' in path else
                 'scipy' if '/scipy.libs/' in path else None)
        if owner is None:
            raise ValueError('Unexpected loaded BLAS library: '+path)
        suffix = '64_' if owner=='numpy' else ''
        handle = loader(path)
        getter = getattr(handle,'scipy_openblas_get_num_threads'+suffix)
        getter.argtypes, getter.restype = [], ctypes.c_int
        config = getattr(handle,'scipy_openblas_get_config'+suffix)
        config.argtypes, config.restype = [], ctypes.c_char_p
        rows.append(dict(owner=owner,path=path,threads=int(getter()),
                         config=config().decode('ascii'),sha256=digest(Path(path))))
    if sorted(r['owner'] for r in rows)!=['numpy','scipy']:
        raise ValueError('Require exactly one loaded NumPy and one SciPy BLAS library')
    return rows


def configure_backend(libraries, threads, backend, loader=ctypes.CDLL):
    """Configure only this fresh research process, before any measured call."""
    for row in libraries:
        suffix = '64_' if row['owner']=='numpy' else ''
        setter = getattr(loader(row['path']),'scipy_openblas_set_num_threads'+suffix)
        setter.argtypes,setter.restype = [ctypes.c_int],None
        setter(threads if backend in ('both',row['owner']) else 1)


def worker(root, threads, reference, backend):
    import numpy as np
    from check_algo07v3_scan_likelihood import fingerprint

    from leo.analysis.localization_v3.hierarchical import hierarchical_bound

    plan = json.loads((root.parent/'plan.json').read_bytes())
    expected = json.loads(reference.read_bytes()) if reference else None
    libraries = library_info()
    if backend!='both':
        configure_backend(libraries,threads,backend)
        libraries = library_info()
    if any(row['threads']!=(threads if backend in ('both',row['owner']) else 1)
           for row in libraries):
        raise ValueError('Loaded BLAS threads differ from declared configuration')
    if sorted(os.sched_getaffinity(0)) != plan['cpus']:
        raise ValueError('Worker CPU affinity differs from plan')
    cases = []
    for index, capture in enumerate(map(Path,plan['captures'])):
        metadata = json.loads((capture/'hardest.json').read_bytes())
        assert digest(capture/'hardest.npz')==metadata['arrays_sha256']
        with np.load(capture/'hardest.npz',allow_pickle=False) as data:
            args = [data[f'argument_{i}'] for i in range(4)]
            kw = dict(metadata['scalar_keywords'])
            kw.update({k.removeprefix('keyword_'):data[k] for k in data.files
                       if k.startswith('keyword_')})
        before = fingerprint((args,kw))
        observations, signature = [], None
        differing = []
        for repeat in range(3):
            began, used = time.perf_counter(), time.process_time()
            result = hierarchical_bound(*args,**kw)
            elapsed, cpu = time.perf_counter()-began,time.process_time()-used
            actual = fingerprint(result)
            if signature is None:
                signature = actual
                np.savez(root/f'case-{index}.npz',**result)
            if expected is not None:
                target = expected['cases'][index]['signature']
                differing = [key for key in target if actual[key]!=target[key]]
                assert actual.keys()==target.keys()
            else:
                differing = [key for key in signature if actual[key]!=signature[key]]
            observations.append(dict(repeat=repeat,seconds=elapsed,cpu_seconds=cpu,
                                     exact=not differing))
            if differing:
                break
        assert before==fingerprint((args,kw))
        cases.append(dict(index=index,capture=str(capture),shape=list(args[1].shape),
                          signature=signature,differing_fields=differing,
                          observations=observations,exact=not differing))
    assert library_info()==libraries
    result = dict(threads=threads,backend=backend,libraries=libraries,cases=cases,
                  exact=all(row['exact'] for row in cases),cpus=sorted(os.sched_getaffinity(0)),
                  process_threads=len(list(Path('/proc/self/task').iterdir())),
                  linux_threads_are_not_simultaneously_active_cpu_slots=True)
    (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,action='append')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--threads',type=int,choices=(1,2,3))
    parser.add_argument('--backend',choices=('both','numpy','scipy'),default='both')
    parser.add_argument('--reference',type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker,args.threads,args.reference,args.backend)
        return
    if not args.capture or not args.output:
        parser.error('--capture and --output required')
    root=args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    root.mkdir(exist_ok=False)
    paths=[Path(__file__),Path('src/leo/analysis/localization_v3/hierarchical.py'),
           Path('tools/check_algo07v3_scan_likelihood.py')]
    for capture in args.capture:
        paths.extend((capture/'hardest.json',capture/'hardest.npz'))
    bindings={str(p.resolve()):digest(p) for p in paths}
    plan=dict(captures=[str(p.resolve()) for p in args.capture],bindings=bindings,
              cpus=[0,1,2],orders=[[1,2,3],[3,2,1]],backend=args.backend,
              production_modified=False,
              captured_kernel_only=True,full_pipeline_speedup=None)
    (root/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    rows, reference, rejected=[],None,set()
    for sequence, order in enumerate(plan['orders']):
        for threads in order:
            if threads in rejected:
                continue
            target=root/f'round-{sequence}-threads-{threads}'
            target.mkdir()
            command=['taskset','-c','0,1,2',sys.executable,'-B',str(Path(__file__).resolve()),
                     '--worker',str(target),'--threads',str(threads),'--backend',args.backend]
            if reference:
                command+=['--reference',str(reference)]
            initial_threads=threads if args.backend=='both' else 1
            env=dict(os.environ,OPENBLAS_NUM_THREADS=str(initial_threads),
                     OMP_NUM_THREADS=str(initial_threads))
            with (target/'worker.log').open('xb') as stream:
                subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,
                               check=True,timeout=120)
            result=json.loads((target/'result.json').read_bytes())
            if reference is None:
                assert threads==1 and result['exact']
                reference=target/'result.json'
            if not result['exact']:
                rejected.add(threads)
            rows.append(dict(sequence=sequence,root=str(target),**result))
            print(json.dumps(dict(sequence=sequence,threads=threads,exact=result['exact'],
                differing_fields=[c['differing_fields'] for c in result['cases']])),flush=True)
    assert all(digest(Path(p))==sha for p,sha in bindings.items())
    assert all(row['libraries']==rows[0]['libraries'] for row in rows if row['threads']==1)
    (root/'result.json').write_text(json.dumps(dict(rows=rows,bindings=bindings,
        rejected_threads=sorted(rejected),production_modified=False,full_pipeline_speedup=None),
        indent=2)+'\n')


if __name__=='__main__':
    main()
