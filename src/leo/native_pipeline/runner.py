"""Sequential, bounded native-stage replay with immutable artifact receipts.

This runner owns processes and files. Numerical components see only explicit
CLI ports. No shell interpolation, report imports, automatic cache or radio IO.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import time

from . import membership

FORMATS = {'executable', 'observations-tsv-v1', 'sources-tsv-v1', 'tracks-tsv-v1',
           'iq-ci16-v1', 'template-c128', 'native-glrt-json-v1', 'location-loc1',
           'json-v1', 'native-glrt-archive-v1'}
KINDS = {'detector', 'projection', 'seed', 'tracking', 'location', 'diagnostic'}
NAME = re.compile(r'^[a-z][a-z0-9_-]*$')


def digest(path):
    return membership.digest(Path(path))


def artifact_digest(path):
    path = Path(path)
    if path.is_file():
        return digest(path)
    if not path.is_dir():
        raise ValueError(f'artifact not found: {path}')
    files = sorted(path.rglob('*'))
    if any(p.is_symlink() for p in files):
        raise ValueError('directory checkpoints may not contain symlinks')
    entries = [(str(p.relative_to(path)),digest(p)) for p in files if p.is_file()]
    return hashlib.sha256(json.dumps(entries,separators=(',',':')).encode()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def finite_json(path):
    def invalid(value):
        raise ValueError(f'nonfinite JSON value: {value}')
    value = json.loads(path.read_text(), parse_constant=invalid)
    # JSON exponents can overflow even without an explicit NaN/Infinity token.
    json.dumps(value, allow_nan=False)
    return value


def validate_artifact(path, spec, paths):
    fmt = spec['format']
    if path.is_dir() != (fmt == 'native-glrt-archive-v1'):
        raise ValueError('artifact file/directory type mismatch')
    if fmt == 'observations-tsv-v1':
        membership.read_observations(path)
    elif fmt in {'tracks-tsv-v1', 'sources-tsv-v1'}:
        observations = membership.read_observations(paths[spec['observations']])
        reader = membership.read_tracks if fmt == 'tracks-tsv-v1' else membership.read_sources
        reader(path, observations)
    elif fmt == 'iq-ci16-v1':
        meta = spec['metadata']
        for key in ('sample_rate_hz', 'receivers', 'sample_count'):
            if type(meta[key]) is not int or meta[key] <= 0:
                raise ValueError(f'invalid IQ {key}')
        if meta['layout'] != 'sample-receiver-iq' or meta['byte_order'] != 'little':
            raise ValueError('unsupported IQ layout')
        if meta['end_counter']-meta['first_counter'] != meta['sample_count']:
            raise ValueError('IQ sample counter range mismatch')
        if path.stat().st_size != meta['sample_count']*meta['receivers']*4:
            raise ValueError('IQ byte count mismatch')
        if not math.isfinite(meta['actual_rf_hz']) or meta['actual_rf_hz'] <= 0:
            raise ValueError('invalid actual RF')
        if meta['time_authority'] not in {'sample-counter-anchor', 'estimated'}:
            raise ValueError('missing time authority')
        if type(meta['first_sample_utc_ns']) is not int or meta['utc_uncertainty_ns'] < 0:
            raise ValueError('invalid sample time mapping')
    elif fmt == 'template-c128':
        if not path.stat().st_size or path.stat().st_size % 16:
            raise ValueError('invalid complex128 template length')
    elif fmt == 'location-loc1':
        with path.open('rb') as stream:
            if stream.read(4) != b'LOC1':
                raise ValueError('invalid LOC1 checkpoint')
    elif fmt in {'json-v1', 'native-glrt-json-v1'}:
        value = finite_json(path)
        if fmt == 'native-glrt-json-v1':
            if not isinstance(value, dict) or not isinstance(value.get('rows'), list):
                raise ValueError('expected native GLRT rows')
            for row in value['rows']:
                if not isinstance(row.get('candidates'), list):
                    raise ValueError('expected native GLRT candidates')
                for c in row['candidates']:
                    for key in ('tracking_cfo_hz', 'exact_score', 'control_score', 'margin'):
                        if not math.isfinite(c[key]):
                            raise ValueError(f'invalid candidate {key}')
    elif fmt == 'native-glrt-archive-v1':
        for name in ('completion.json','capture-manifest.json','inventory.json'):
            finite_json(path/name)


def validate_plan(plan):
    if plan.get('schema') != 'leo-native-replay/v1':
        raise ValueError('unsupported replay schema')
    if plan.get('execution') != {'mode': 'serial', 'workers': 1}:
        raise ValueError('only explicit serial execution is implemented')
    inputs = plan['inputs']
    known = set(inputs)
    formats = {}
    for key, spec in inputs.items():
        if key == 'output-dir' or not NAME.fullmatch(key) or spec['format'] not in FORMATS:
            raise ValueError('invalid input name or format')
        if not re.fullmatch('[0-9a-f]{64}', spec['sha256']):
            raise ValueError('input requires a SHA-256 digest')
        formats[key] = spec['format']
    for stage in plan['stages']:
        name = stage['id']
        if name == 'output-dir' or not NAME.fullmatch(name) or name in known or stage['kind'] not in KINDS:
            raise ValueError('invalid or duplicate stage')
        if stage['format'] not in FORMATS-{'executable'}:
            raise ValueError('unsupported output format')
        if formats.get(stage['executable']) != 'executable':
            raise ValueError('stage executable must be a pinned executable input')
        if not isinstance(stage['argv'], list) or not all(isinstance(a, str) for a in stage['argv']):
            raise ValueError('argv must be a list of strings')
        for arg in stage['argv']:
            if arg.startswith('@') and arg != '@output-dir' and arg[1:] not in known:
                raise ValueError(f'unknown or forward artifact reference: {arg}')
        timeout = stage['timeout_s']
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError('stage timeout must be in (0, 300] seconds')
        if stage['format'] in {'tracks-tsv-v1', 'sources-tsv-v1'}:
            if formats.get(stage.get('observations')) != 'observations-tsv-v1':
                raise ValueError('track/source output needs an observation checkpoint')
        known.add(name)
        formats[name] = stage['format']
        for child in stage.get('artifacts',[]):
            key = child['id']
            relative = Path(child['path'])
            if key == 'output-dir' or not NAME.fullmatch(key) or key in known:
                raise ValueError('duplicate or invalid output artifact name')
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                raise ValueError('output artifact must stay inside its stage directory')
            if child['format'] not in FORMATS-{'executable','native-glrt-archive-v1'}:
                raise ValueError('unsupported secondary artifact format')
            if child['format'] in {'tracks-tsv-v1','sources-tsv-v1'} and formats.get(child.get('observations')) != 'observations-tsv-v1':
                raise ValueError('secondary artifact needs an earlier observation checkpoint')
            known.add(key)
            formats[key] = child['format']
    if not plan['stages']:
        raise ValueError('empty replay plan')
    for spec in inputs.values():
        if spec['format'] in {'tracks-tsv-v1', 'sources-tsv-v1'}:
            if spec.get('observations') not in inputs or formats[spec['observations']] != 'observations-tsv-v1':
                raise ValueError('input needs an observation checkpoint')


def run(plan_path, output):
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = finite_json(plan_path)
    validate_plan(plan)
    # Preserve executable symlink spelling: resolving a venv's Python symlink
    # changes its environment even when executable bytes have the same digest.
    paths = {key:Path(os.path.abspath(plan_path.parent/spec['path'])) for key,spec in plan['inputs'].items()}
    for key, spec in plan['inputs'].items():
        if artifact_digest(paths[key]) != spec['sha256']:
            raise ValueError(f'input digest mismatch: {key}')
        validate_artifact(paths[key], spec, paths)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'plan.json', plan)
    receipt = {'schema':'leo-native-replay-receipt/v1', 'status':'running',
               'plan_sha256':digest(plan_path), 'platform':platform.platform(),
               'machine':platform.machine(), 'python':platform.python_version(),
               'runner_sha256':digest(__file__),
               'package_sha256':{p.name:digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
               'cpu_affinity':sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
               'thread_environment':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
               'stages':[]}
    write_json(output/'receipt.json', receipt)
    try:
        for stage in plan['stages']:
            name = stage['id']
            target = output/(name+'.output')
            stderr = output/(name+'.stderr')
            products = output/(name+'.artifacts')
            argv = [str(paths[stage['executable']])]+[
                str(products) if a == '@output-dir' else
                str(paths[a[1:]]) if a.startswith('@') else a for a in stage['argv']]
            started = time.monotonic()
            record = {'id':name, 'kind':stage['kind'], 'argv':argv, 'status':'running'}
            receipt['stages'].append(record)
            with target.open('wb') as out, stderr.open('wb') as err:
                proc = subprocess.Popen(argv, stdout=out, stderr=err, cwd=output,
                                        start_new_session=True, env={**os.environ, 'LC_ALL':'C'})
                try:
                    code = proc.wait(timeout=stage['timeout_s'])
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    record.update(status='timeout', wall_s=time.monotonic()-started)
                    raise
                except BaseException:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    record.update(status='cancelled', wall_s=time.monotonic()-started)
                    raise
            record.update(exit_code=code, wall_s=time.monotonic()-started)
            if code:
                raise RuntimeError(f'{name} exited {code}; see {stderr}')
            validate_artifact(target, stage, paths)
            # Algorithm timers are reported separately from process wall time.
            timers = []
            if stage['kind'] in {'tracking', 'seed'}:
                for line in stderr.read_text().splitlines():
                    if line.startswith('TIMING\treconstruct_s\t'):
                        timers.append(float(line.split('\t')[2]))
                    elif line.startswith('{'):
                        value = json.loads(line)
                        if 'reconstruct_s' in value:
                            timers.append(float(value['reconstruct_s']))
            if timers:
                if not all(math.isfinite(t) and t >= 0 for t in timers):
                    raise ValueError('invalid algorithm timer')
                record['algorithm_s'] = sum(timers)
            if stage.get('expected_sha256') and digest(target) != stage['expected_sha256']:
                raise ValueError(f'{name} output differs from frozen expectation')
            record.update(output_sha256=digest(target),
                          stderr_sha256=digest(stderr))
            paths[name] = target
            record['artifacts'] = []
            for child in stage.get('artifacts',[]):
                path = (products/child['path']).resolve()
                if not path.is_relative_to(products.resolve()):
                    raise ValueError('output artifact escapes stage directory')
                validate_artifact(path,child,paths)
                child_digest = digest(path)
                if child.get('expected_sha256') and child_digest != child['expected_sha256']:
                    raise ValueError('secondary artifact differs from frozen expectation')
                paths[child['id']] = path
                record['artifacts'].append({'id':child['id'],'sha256':child_digest})
            record['status'] = 'complete'
            write_json(output/'receipt.json', receipt)
        # Mutation of upstream artifacts invalidates the entire run.
        for key,spec in plan['inputs'].items():
            if artifact_digest(paths[key]) != spec['sha256']:
                raise ValueError(f'input changed during replay: {key}')
        for record in receipt['stages']:
            if digest(paths[record['id']]) != record['output_sha256']:
                raise ValueError('intermediate output changed during replay')
            for child in record['artifacts']:
                if digest(paths[child['id']]) != child['sha256']:
                    raise ValueError('secondary artifact changed during replay')
        receipt['status'] = 'complete'
    except BaseException as exc:
        receipt.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        if receipt['stages'] and receipt['stages'][-1]['status'] == 'running':
            receipt['stages'][-1]['status'] = 'failed'
        raise
    finally:
        write_json(output/'receipt.json', receipt)
    return receipt
