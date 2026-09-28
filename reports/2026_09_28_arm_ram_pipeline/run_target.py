"""Bounded, saved-IQ-only ARM experiment. Never opens radio devices."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
RATES = (2500000, 5000000, 7500000, 10000000)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def phases():
    result = []
    for rate in RATES:
        for method in ('D', 'goal40mag'):
            for mode, schedule in [('isolated', 'fixed-period'),
                                   ('concurrent', 'fixed-period'),
                                   ('concurrent', 'saved-arrival-offsets')]:
                repeats = 3 if rate == 2500000 and mode == 'concurrent' else 1
                for repeat in range(repeats):
                    jobs = (48 if rate == 2500000 else 12) if mode == 'isolated' else (120 if rate == 2500000 else 60)
                    name = f'{rate}-{method}-{mode}-{schedule}-r{repeat}'
                    result.append(dict(name=name, file=name+'.jsonl', method=method,
                                       mode=mode, rate_hz=rate, schedule_kind=schedule, jobs=jobs))
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('prior_transport', HERE.parent / '2026_09_27_plutoplus_static_arm/concurrent/run_phase.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ssh = module.SSH

    def remote(command, timeout=30):
        return subprocess.run(ssh + [command], capture_output=True, timeout=timeout, check=True)

    metadata = remote('uname -a; cat /sys/devices/system/cpu/online; cat /proc/meminfo; cat /proc/mounts; ps')
    (a.output / 'device-before.txt').write_bytes(metadata.stdout)
    target = remote('mktemp -d /mnt/glrtbench/ram-pipeline.XXXXXX').stdout.decode().strip()
    if not target.startswith('/mnt/glrtbench/ram-pipeline.') or any(c.isspace() for c in target):
        raise ValueError('unexpected target directory')
    inventory = phases()
    manifest = json.loads((a.prepared / 'inputs.json').read_text())
    hashes = {'data/' + name: sha for name, sha in manifest['files'].items()}
    for method in ('D', 'goal40mag'):
        hashes['arm-'+method] = digest(a.prepared / ('arm-'+method))
    for name, expected in hashes.items():
        if digest(a.prepared / name) != expected:
            raise ValueError('staging source changed')
    checks = a.output / 'SHA256SUMS'
    checks.write_text(''.join(f'{sha}  {name}\n' for name, sha in hashes.items()))
    bundle = a.output / 'transfer.tar'
    with tarfile.open(bundle, 'w') as archive:
        for name in hashes:
            archive.add(a.prepared / name, arcname=name)
        archive.add(checks, arcname='SHA256SUMS')
    with bundle.open('rb') as source:
        subprocess.run(ssh + [f'tar -xf - -C {shlex.quote(target)}'], stdin=source, capture_output=True, check=True, timeout=180)
    verification = remote(f'cd {shlex.quote(target)} && sha256sum -c SHA256SUMS', timeout=60)
    (a.output / 'target-hashes.txt').write_bytes(verification.stdout)
    bundle.unlink()
    receipt = dict(complete=False, target=target, host='192.168.1.15',
                   input_manifest_sha256=digest(a.prepared / 'inputs.json'),
                   source_hashes={name: digest(HERE / name) for name in ('ram_pipeline.c', 'prepare.py', 'run_target.py')},
                   staged_hashes=hashes, phases=inventory)
    save(a.output / 'run.json', receipt)
    for phase in inventory:
        rate = phase['rate_hz']
        producer = -1 if phase['mode'] == 'isolated' else 1
        command = f'cd {shlex.quote(target)}/data && '
        if phase['schedule_kind'] == 'saved-arrival-offsets':
            command += f"head -n {phase['jobs']} counter-arrivals-{rate}.txt > active-offsets.txt && "
        command += f"../arm-{phase['method']} cases-{rate}.txt {rate} {phase['jobs']} 120 0 {producer} 2 3"
        if phase['schedule_kind'] == 'saved-arrival-offsets':
            command += ' active-offsets.txt'
        result = subprocess.run(ssh + [command], capture_output=True, timeout=140)
        (a.output / phase['file']).write_bytes(result.stdout)
        (a.output / (phase['name']+'.stderr')).write_bytes(result.stderr)
        phase['returncode'] = result.returncode
        phase['sha256'] = digest(a.output / phase['file'])
        save(a.output / 'run.json', receipt)
        if result.returncode:
            raise RuntimeError(f"failed phase {phase['name']}: {result.stderr.decode()}")
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        if rows[-1].get('type') != 'complete' or not rows[-1].get('complete'):
            raise RuntimeError('missing terminal completion')
        end = rows[-1]
        print(phase['name'], 'processed', end['processed'], 'dropped', end['dropped_queue_full'], flush=True)
    (a.output / 'device-after.txt').write_bytes(remote('cat /proc/meminfo; ps').stdout)
    receipt['complete'] = True
    save(a.output / 'run.json', receipt)


if __name__ == '__main__':
    main()
