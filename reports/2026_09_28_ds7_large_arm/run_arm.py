"""Replay the frozen larger DS7 cohort on one physical ARM core, without RF."""
import argparse
import hashlib
import importlib.util
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import threading
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / '2026_09_28_arm_ram_pipeline'
NATIVE_INPUTS = Path('/tmp/leo-static-arm15-20260927-v3')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def validate_batch(rows, capture):
    expected = [(capture['session_id'], index) for index in capture['visit_indices']]
    actual = [(row['session_id'], row['visit_index']) for row in rows]
    if actual != expected or len(set(actual)) != len(expected):
        raise ValueError('batch membership/order differs from frozen plan')
    for row in rows:
        if row['rate_hz'] != capture['sample_rate_hz'] or row['manifest_sha256'] != capture['manifest_sha256']:
            raise ValueError('batch source binding differs')
        if row['shape'] != [row['rate_hz'] * 120 // 1000, 2, 2] or row['dtype'] != 'int16':
            raise ValueError('batch geometry differs from 120ms dual CI16')
    return rows


def validate_phase(raw, rows):
    records = [json.loads(line) for line in raw.splitlines()]
    if len(records) != len(rows) + 2 or records[0].get('type') != 'ready' or records[-1].get('type') != 'complete':
        raise ValueError('phase record inventory')
    ready, end = records[0], records[-1]
    if ready['rate_hz'] != rows[0]['rate_hz'] or ready['jobs'] != len(rows) or end['jobs'] != len(rows):
        raise ValueError('wrong ARM rate/job count')
    if ready['method'] != 'goal40mag' or ready['mode'] != 'isolated' or ready['consumer_core'] != 0 or ready['receivers'] != 2:
        raise ValueError('wrong ARM workload')
    if not end['complete'] or end['processed'] != len(rows) or end['dropped_queue_full'] or end['detector_failures']:
        raise ValueError('missing/dropped/failed ARM jobs')
    jobs = records[1:-1]
    for index, (job, context) in enumerate(zip(jobs, rows, strict=True)):
        case_id = f"ds7-{context['session_id']}-v{context['visit_index']}"
        if job['index'] != index or job['case_id'] != case_id or job['status'] != 'processed':
            raise ValueError('ARM job identity differs')
        if [rx['receiver'] for rx in job['receivers']] != [0, 1]:
            raise ValueError('receiver inventory')
        job['context'] = context
    return jobs, ready, end


def transfer_http(archive_path, ssh, target, bind_address):
    """Expose exactly one owned archive to the target for one bounded transfer."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.client_address[0] != '192.168.1.15' or self.path != '/batch.tar.gz':
                self.send_error(403)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(archive_path.stat().st_size))
            self.end_headers()
            with archive_path.open('rb') as stream:
                shutil.copyfileobj(stream, self.wfile, length=1024 * 1024)

        def log_message(self, *unused):
            pass

    server = HTTPServer((bind_address, 0), Handler)
    server.timeout = 180
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    url = f'http://{bind_address}:{server.server_port}/batch.tar.gz'
    try:
        return subprocess.run(ssh + [f'wget -q -O - {shlex.quote(url)} | gzip -dc | tar -xf - -C {shlex.quote(target)}'], capture_output=True, timeout=180)
    finally:
        server.server_close()
        thread.join(timeout=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--plan', type=Path, default=HERE / 'plan.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--binary', type=Path, default=Path('/var/tmp/leo-arm-ram-20260928/arm-goal40mag'))
    parser.add_argument('--resume-prefix', type=Path)
    parser.add_argument('--http-bind', default='192.168.1.142')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    build = json.loads((PRIOR / 'arm-goal40mag.build.json').read_text())
    if sha(args.binary) != build['binary_sha256'] or sha(PRIOR / 'ram_pipeline.c') != build['worker_sha256']:
        raise ValueError('qualified ARM binary/worker changed')
    spec = importlib.util.spec_from_file_location('prior_transport', HERE.parent / '2026_09_27_plutoplus_static_arm/concurrent/run_phase.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    ssh = transport.SSH

    def remote(command, timeout=30):
        return subprocess.run(ssh + [command], capture_output=True, timeout=timeout, check=True)

    (args.output / 'device-before.txt').write_bytes(remote('uname -a; cat /sys/devices/system/cpu/online; cat /proc/meminfo; ps').stdout)
    target = remote('mktemp -d /mnt/glrtbench/ds7-large.XXXXXX').stdout.decode().strip()
    if not target.startswith('/mnt/glrtbench/ds7-large.') or any(c.isspace() for c in target):
        raise ValueError('unexpected target directory')
    quoted = shlex.quote(target)
    with args.binary.open('rb') as source:
        subprocess.run(ssh + [f'cat > {quoted}/arm-goal40mag && chmod 755 {quoted}/arm-goal40mag'], stdin=source, capture_output=True, check=True, timeout=60)
    binary_hash = remote(f'sha256sum {quoted}/arm-goal40mag').stdout.decode().split()[0]
    if binary_hash != build['binary_sha256']:
        raise ValueError('target binary hash differs')
    old_templates = json.loads((NATIVE_INPUTS / 'manifest.json').read_text())['templates']
    expected = sum(len(c['visit_indices']) for c in plan['captures'])
    receipt = dict(schema='ds7-large-arm-run/v1', complete=False, planned_calls=expected,
                   calls=0, failed_calls=0, batches=[], target=target, host='192.168.1.15',
                   binary_sha256=binary_hash, worker_sha256=build['worker_sha256'],
                   plan_sha256=sha(args.plan), runner_sha256=sha(Path(__file__)),
                   dataset_sha256=plan['dataset_sha256'],
                   scope='physical ARM CPU0; saved-IQ isolated rank6/confirm1; warmups excluded; no RF; no concurrent capture')
    prefix_rows = []
    skip_batches = 0
    if args.resume_prefix:
        prefix = args.resume_prefix.resolve()
        previous = json.loads((prefix / 'run.json').read_text())
        prefix_rows = [json.loads(line) for line in (prefix / 'rows.jsonl').read_text().splitlines()]
        if previous['plan_sha256'] != receipt['plan_sha256'] or previous['binary_sha256'] != binary_hash:
            raise ValueError('resume scientific/input binding differs')
        if previous['calls'] != len(prefix_rows) or previous['failed_calls']:
            raise ValueError('resume prefix accounting')
        offset = 0
        for entry, capture in zip(previous['batches'], plan['captures'], strict=False):
            raw_path = prefix / entry['file']
            if entry['returncode'] or sha(raw_path) != entry['sha256']:
                raise ValueError('resume phase integrity')
            count = len(capture['visit_indices'])
            contexts = [job['context'] for job in prefix_rows[offset:offset + count]]
            validate_batch(contexts, capture)
            jobs, _, _ = validate_phase(raw_path.read_bytes(), contexts)
            if jobs != prefix_rows[offset:offset + count]:
                raise ValueError('resume combined rows differ from raw phase')
            receipt['batches'].append({**entry, 'source_directory': str(prefix)})
            offset += count
            skip_batches += 1
        if offset != len(prefix_rows):
            raise ValueError('resume prefix is not an exact complete batch prefix')
        receipt['calls'] = len(prefix_rows)
        receipt['prefix'] = dict(directory=str(prefix), run_sha256=sha(prefix / 'run.json'),
                                 rows_sha256=sha(prefix / 'rows.jsonl'), runner_sha256=previous['runner_sha256'])
    save(args.output / 'run.json', receipt)
    started = time.monotonic()
    staging = args.output / 'staging'
    staging.mkdir()
    with (args.output / 'rows.jsonl').open('x') as combined:
        for job in prefix_rows:
            combined.write(json.dumps(job, allow_nan=False) + '\n')
        combined.flush()
        for ordinal, capture in enumerate(plan['captures']):
            if ordinal < skip_batches:
                continue
            if time.monotonic() - started > 2400:
                raise TimeoutError('bounded ARM experiment elapsed')
            # Atomic per-capture manifests let extraction and ARM work overlap.
            partial = args.inputs / 'batches' / (capture['session_id'] + '.json')
            while not partial.exists():
                if time.monotonic() - started > 2400:
                    raise TimeoutError('input batch wait exceeded bounded run')
                time.sleep(1)
            batch_manifest = json.loads(partial.read_text())
            if not batch_manifest['complete'] or batch_manifest['plan_sha256'] != receipt['plan_sha256'] or batch_manifest['dataset_sha256'] != receipt['dataset_sha256']:
                raise ValueError('input batch seal differs')
            rows = validate_batch(batch_manifest['rows'], capture)
            batch_name = f'batch-{ordinal:03d}'
            local = staging / batch_name
            local.mkdir()
            lines = []
            for row in rows:
                source = args.inputs / row['file']
                if source.parent.resolve() != args.inputs.resolve() or sha(source) != row['sha256']:
                    raise ValueError('IQ payload binding')
                iq = np.load(source, allow_pickle=False)
                if list(iq.shape) != row['shape'] or str(iq.dtype) != row['dtype']:
                    raise ValueError('IQ payload geometry')
                case_id = f"ds7-{row['session_id']}-v{row['visit_index']}"
                raw_name = case_id + '.ci16'
                np.asarray(iq, dtype='<i2').tofile(local / raw_name)
                template = old_templates[f"{row['rate_hz']}-{row['target']['edge']}"]
                for label in ('exact', 'control'):
                    name = template[label]
                    if sha(NATIVE_INPUTS / 'data' / name) != template[label + '_sha256']:
                        raise ValueError('qualified template changed')
                    if not (local / name).exists():
                        shutil.copyfile(NATIVE_INPUTS / 'data' / name, local / name)
                lines.append(f"{raw_name} {template['exact']} {template['control']} {case_id}")
            (local / 'cases.txt').write_text('\n'.join(lines) + '\n')
            hashes = {path.name: sha(path) for path in sorted(local.iterdir())}
            (local / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in hashes.items()))
            archive_path = staging / (batch_name + '.tar.gz')
            with tarfile.open(archive_path, 'w:gz', compresslevel=1) as archive:
                archive.add(local, arcname=batch_name)
            transferred = transfer_http(archive_path, ssh, target, args.http_bind)
            (args.output / (batch_name + '.transfer.stderr')).write_bytes(transferred.stderr)
            if transferred.returncode:
                raise RuntimeError('transfer failed; diagnostic retained')
            rate = capture['sample_rate_hz']
            command = f'cd {quoted}/{batch_name} && sha256sum -c SHA256SUMS >&2 && ../arm-goal40mag cases.txt {rate} {len(rows)} 120 0 -1 2 3'
            result = subprocess.run(ssh + [command], capture_output=True, timeout=140)
            filename = batch_name + '.jsonl'
            (args.output / filename).write_bytes(result.stdout)
            (args.output / (batch_name + '.stderr')).write_bytes(result.stderr)
            entry = dict(name=batch_name, session_id=capture['session_id'], file=filename,
                         rate_hz=rate, jobs=len(rows), returncode=result.returncode,
                         sha256=sha(args.output / filename), input_batch_sha256=sha(partial), staged_hashes=hashes)
            receipt['batches'].append(entry)
            save(args.output / 'run.json', receipt)
            if result.returncode:
                raise RuntimeError('ARM batch failed; raw receipt retained')
            jobs, _, _ = validate_phase(result.stdout, rows)
            for job in jobs:
                combined.write(json.dumps(job, allow_nan=False) + '\n')
            combined.flush()
            receipt['calls'] += len(jobs)
            save(args.output / 'run.json', receipt)
            print(json.dumps(dict(batch=ordinal + 1, calls=receipt['calls'], expected=expected, rate_hz=rate)), flush=True)
            # Remove only temporary copies created by this runner; sources and
            # target-side staged IQ plus all result/hash receipts are retained.
            shutil.rmtree(local)
            archive_path.unlink()
    full = args.inputs / 'inputs.json'
    while not full.exists():
        if time.monotonic() - started > 2400:
            raise TimeoutError('final input seal unavailable')
        time.sleep(1)
    manifest = json.loads(full.read_text())
    if not manifest['complete'] or manifest['plan_sha256'] != receipt['plan_sha256']:
        raise ValueError('final input seal differs')
    actual_contexts = [json.loads(line)['context'] for line in (args.output / 'rows.jsonl').read_text().splitlines()]
    if actual_contexts != manifest['rows']:
        raise ValueError('final input inventory differs from executed inputs')
    receipt.update(complete=receipt['calls'] == expected, input_manifest_sha256=sha(full),
                   rows_sha256=sha(args.output / 'rows.jsonl'), wall_s=time.monotonic() - started)
    (args.output / 'device-after.txt').write_bytes(remote('cat /proc/meminfo; ps').stdout)
    save(args.output / 'run.json', receipt)


if __name__ == '__main__':
    main()
