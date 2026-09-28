"""Bind DS7 saved IQ and qualified ARM sources to a new RAM experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / '2026_09_27_plutoplus_static_arm'
DS7 = HERE.parent / '2026_09_28_ds7_glrt_benchmark'
ARM_BASE = Path('/tmp/leo-static-arm15-20260927-v3')
ARM_OPT = PRIOR / 'optimize/work/goal40mag'
RATES = (2500000, 5000000, 7500000, 10000000)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def prepare(inputs, output):
    manifest = json.loads((inputs / 'inputs.json').read_text())
    if sha(inputs / 'inputs.json') != sha(DS7 / 'inputs.json') or not manifest['complete']:
        raise ValueError('DS7 frozen manifest mismatch')
    output.mkdir(parents=True, exist_ok=False)
    data = output / 'data'
    data.mkdir()
    old = json.loads((ARM_BASE / 'manifest.json').read_text())
    exported = []
    files = {}
    for rate in RATES:
        rows = [r for r in manifest['rows'] if r['rate_hz'] == rate]
        case_lines = []
        for row in rows:
            path = inputs / row['file']
            if path.parent.resolve() != inputs.resolve() or sha(path) != row['sha256']:
                raise ValueError('DS7 payload binding')
            iq = np.load(path, allow_pickle=False)
            if list(iq.shape) != row['shape'] or str(iq.dtype) != row['dtype'] or iq.shape[1:] != (2, 2):
                raise ValueError('DS7 payload geometry')
            case_id = f"ds7-{row['session_id']}-v{row['visit_index']}"
            raw = case_id + '.ci16'
            np.asarray(iq, dtype='<i2').tofile(data / raw)
            key = f"{rate}-{row['target']['edge']}"
            template = old['templates'][key]
            for label in ('exact', 'control'):
                name = template[label]
                source = ARM_BASE / 'data' / name
                if sha(source) != template[label + '_sha256']:
                    raise ValueError('frozen template changed')
                if not (data / name).exists():
                    shutil.copyfile(source, data / name)
                files[name] = sha(data / name)
            files[raw] = sha(data / raw)
            case_lines.append(f"{raw} {template['exact']} {template['control']} {case_id}")
            exported.append({'case_id': case_id, 'raw': raw, 'sha256': files[raw], 'source': row})
        name = f'cases-{rate}.txt'
        (data / name).write_text('\n'.join(case_lines) + '\n')
        files[name] = sha(data / name)
        offsets = [(r['sample_start_counter'] - rows[0]['sample_start_counter']) * 1000 / rate for r in rows]
        gaps = [b - a for a, b in zip(offsets, offsets[1:])]
        if any(gap < 120 for gap in gaps):
            raise ValueError('source cadence overlaps 120ms capture')
        # Repeat the measured finite block; the seam uses its mean measured gap.
        # This is an explicit synthetic periodic continuation, not new recorded data.
        cycle = offsets[-1] + sum(gaps) / len(gaps)
        schedule = [cycle * (j // len(rows)) + offsets[j % len(rows)] for j in range(500)]
        name = f'counter-arrivals-{rate}.txt'
        (data / name).write_text(''.join(f'{value:.9f}\n' for value in schedule))
        files[name] = sha(data / name)
    save(output / 'inputs.json', {
        'schema': 'arm-ram-inputs/v1', 'source_manifest_sha256': sha(inputs / 'inputs.json'),
        'dataset_sha256': manifest['dataset_sha256'], 'rows': exported, 'files': files,
        'schedule_scope': 'source-counter start offsets; periodic continuation with mean observed gap at seam',
        'workload': 'native ARM rank-six/confirm-one; not full server eleven-window/eight-candidate GLRT',
    })


def build(output, host=False):
    source = HERE / 'ram_pipeline.c'
    if not source.exists():
        raise ValueError('worker source missing')
    for name, root in [('D', ARM_BASE), ('goal40mag', ARM_OPT)]:
        if name == 'D':
            receipt_path = root / 'arm/build.json'
            receipt = json.loads(receipt_path.read_text())
            command = receipt['methods']['D']['command'].copy()
        else:
            receipt_path = root / 'arm.build.json'
            receipt = json.loads(receipt_path.read_text())
            command = receipt['command'].copy()
        expected = receipt['sources']
        for path, digest in expected.items():
            if sha(root / path) != digest:
                raise ValueError(f'qualified source changed: {root / path}')
        snapshot = output / 'sources' / name
        if not snapshot.exists():
            shutil.copytree(root / 'src', snapshot / 'src')
        for path, digest in expected.items():
            if sha(snapshot / path) != digest:
                raise ValueError('snapshot binding')
        command = [str(snapshot) + arg[len(str(root)):] if arg.startswith(str(root)) else arg for arg in command]
        probe = str(snapshot / 'src/native_presence/probe.c')
        command[command.index(probe)] = str(source)
        flavor = 'host-asan' if host else 'arm'
        binary = output / f'{flavor}-{name}'
        if binary.exists():
            raise FileExistsError(binary)
        command[-1] = str(binary)
        command.insert(1, '-pthread')
        if host:
            command[0] = 'gcc'
            command = [arg for arg in command if not arg.startswith(('--sysroot=', '-mcpu=', '-mfpu=', '-mfloat-abi='))]
            command = ['-lfftw3f' if arg.endswith('/libfftw3f.a') else arg for arg in command]
            command[1:1] = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie']
        result = subprocess.run(command, capture_output=True, timeout=120)
        binary.with_suffix('.stderr').write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        save(binary.with_suffix('.build.json'), {
            'command': command, 'binary_sha256': sha(binary), 'worker_sha256': sha(source),
            'scientific_sources': expected, 'source_snapshot': str(snapshot),
            'qualified_receipt_sha256': sha(receipt_path),
            'compiler': subprocess.check_output([command[0], '--version'], text=True),
            'fp32_fftw_archive_sha256': sha(Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')),
            'scope': 'same qualified reduced ARM kernel; new producer/consumer RAM harness',
        })


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('prepare', 'build', 'host'))
    p.add_argument('--inputs', type=Path, default=Path('/tmp/leo-ds7-glrt-20260928'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.inputs.resolve(), a.output.resolve())
    else:
        build(a.output.resolve(), a.action == 'host')
