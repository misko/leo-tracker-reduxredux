"""Bounded research probe: share integer reference loads across two epochs."""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from profile_algo07_glrt import PROFILE, use_source
from stage_native_glrt_runtime import digest, verify, verify_files


def transform(grid):
    start = grid.index('            for (npy_intp epoch = 0; epoch < valid_epochs; ++epoch) {')
    end = grid.index('                support[epoch] += 1;', start)
    end = grid.index('\n            }', end) + len('\n            }')
    original = grid[start:end]
    norm = original[original.index('                double received_energy ='):]
    norm = norm[:norm.rindex('\n            }')]
    accumulators = '\n'.join(
        f'                __m256i {part}{lane}{group} = _mm256_setzero_si256();'
        for lane in range(2) for part in ('r', 'i') for group in range(3))
    dots = []
    stores = []
    for part, reference in [('r', 'qreal'), ('i', 'qimag')]:
        for group in range(3):
            dots.append(f'''                    {{
                        const __m256i q = _mm256_loadu_si256(
                            (const __m256i *)({reference}+j+{group*16}));
                        {part}0{group} = _mm256_dpwssd_avx_epi32({part}0{group}, x0, q);
                        {part}1{group} = _mm256_dpwssd_avx_epi32({part}1{group}, x1, q);
                    }}''')
            for lane in range(2):
                stores.append(f'                _mm256_storeu_si256((__m256i *)'
                              f'(c{part}[{lane}]+{group*8}), {part}{lane}{group});')
    paired = '''#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)
            for (npy_intp first = 0; first < valid_epochs; first += 2) {
                const npy_intp second = first+1 < valid_epochs ? first+1 : first;
''' + accumulators + '''
                for (npy_intp i = 0; i < reference_count; ++i) {
                    const __m256i x0 = _mm256_set1_epi32((int32_t)packed[base+first+i]);
                    const __m256i x1 = _mm256_set1_epi32((int32_t)packed[base+second+i]);
                    const npy_intp j = i * 48;
''' + '\n'.join(dots) + '''
                }
                int32_t cr[2][24], ci[2][24];
''' + '\n'.join(stores) + '''
                for (int lane = 0; lane < 2 && first+lane < valid_epochs; ++lane) {
                    const npy_intp epoch = first+lane;
                    const npy_intp position = base+epoch;
                    for (int f = 0; f < 24; ++f) {
                        correlation_real[f] = cr[lane][f] / scale;
                        correlation_imag[f] = ci[lane][f] / scale;
                    }
''' + norm + '''
                }
            }
#else
''' + original + '\n#endif'
    return grid[:start] + paired + grid[end:]


def build(source, output):
    source, output = source.resolve(strict=True), PROFILE.destination(output)
    if not output.is_relative_to('/srv/bulk/leo/research') or output.exists():
        raise ValueError('New private output required')
    receipt_path = source/'screen-probe.json'
    before = digest(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    if receipt['screen_kind'] != 'integer_vnni':
        raise ValueError('Pinned integer source required')
    verify_files(source, receipt['files_sha256'])
    output.mkdir()
    for name in receipt['files_sha256']:
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
    name = 'src/leo/analysis/starlink/_native_acquisition_grid.inc'
    (output/name).write_text(transform((source/name).read_text()))
    command = [x.replace(str(source), str(output)) for x in receipt['compile_command']]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    inventory = {n: digest(output/n) for n in receipt['files_sha256']}
    changes = sorted(n for n in inventory if inventory[n] != receipt['files_sha256'][n])
    if len(changes) != 2 or name not in changes or not any(n.endswith('.so') for n in changes):
        raise ValueError('Unexpected research composition')
    verify_files(source, receipt['files_sha256'])
    if digest(receipt_path) != before:
        raise ValueError('Source changed')
    result = dict(source=str(source), source_receipt_sha256=before,
                  files_sha256=inventory, changes=changes, compile_command=command,
                  compiler_stderr=completed.stderr, tool_sha256=digest(Path(__file__)),
                  production_modified=False, qualification='research scheduling only')
    PROFILE.write_new(output/'epoch-pair.json', result)
    return dict(output=str(output), changes=changes)


def run(candidate, installed, pin, fixture, output, limit):
    import numpy as np

    if not 1 <= limit <= 16:
        raise ValueError('One to sixteen windows required')
    receipt_path = candidate/'epoch-pair.json'
    receipt_pin = digest(receipt_path)
    build_receipt = json.loads(receipt_path.read_text())
    if digest(Path(__file__)) != build_receipt['tool_sha256']:
        raise ValueError('Probe changed since build')
    verify_files(candidate, build_receipt['files_sha256'])
    verify(installed, pin)
    if not PROFILE.verify(fixture/'frozen.json')['verified']:
        raise ValueError('Fixture changed')
    use_source(installed)
    from leo.analysis.starlink import coarse_screen
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, production_glrt

    extension = next((candidate/'src/leo/analysis/starlink').glob('_native_acquisition*.so'))
    spec = importlib.util.spec_from_file_location('_paired._native_acquisition', extension)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    if native.folded_anchor_score_grid_backend() != 'avx2_fma':
        raise RuntimeError('Explicit AVX-VNNI hardware required')
    original = coarse_screen.screen_grid
    calls = []

    def checked(reference, acquisition, *args):
        order = [('baseline', reference), ('candidate', native)]
        if len(calls) % 2:
            order.reverse()
        results, times = {}, {}
        for label, module in order:
            began = time.perf_counter()
            results[label] = original(module, acquisition, *args)
            times[label] = time.perf_counter()-began
        left, right = [np.asarray(results[k]) for k in ('baseline', 'candidate')]
        np.testing.assert_array_equal(left.view(np.uint64), right.view(np.uint64))
        calls.append(dict(seconds=times, shape=list(left.shape), exact_values=left.size,
                          order=[x[0] for x in order]))
        return results['candidate']

    rows = json.loads((fixture/'input.json').read_text())['windows'][:limit]
    baseline = json.loads((fixture/'baseline/result.json').read_text())
    expected = {r['visit']: r['receivers'] for r in baseline['windows']}
    coarse_screen.screen_grid = checked
    try:
        for row in rows:
            window = VerifiedFastWindow(row['sequence'], row['iq_sha256'], row['acquisition'],
                                        row['target'], np.load(fixture/row['samples'],
                                                              allow_pickle=False),
                                        row['sample_rate_hz'])
            actual = [r.model_dump(mode='json') for r in
                      production_glrt(window, tuple(row['receiver_ids']))]
            if actual != expected[row['visit']]:
                raise ValueError('Complete detector output changed')
    finally:
        coarse_screen.screen_grid = original
    verify_files(candidate, build_receipt['files_sha256'])
    verify(installed, pin)
    after = PROFILE.verify(fixture/'frozen.json')
    if not after['verified'] or digest(receipt_path) != receipt_pin:
        raise ValueError('Frozen state changed')
    totals = {k: sum(r['seconds'][k] for r in calls) for k in ('baseline', 'candidate')}
    result = dict(fixture=str(fixture), windows=len(rows), calls=calls, totals=totals,
                  grid_speedup=totals['baseline']/totals['candidate'],
                  complete_receiver_outputs_exact=True, frozen_after=after,
                  runtime_root=str(installed), runtime_pin=pin, build_pin=receipt_pin,
                  scope='Alternating coarse-grid calls; not whole-detector timing',
                  production_modified=False)
    PROFILE.write_new(output, result)
    return {k: v for k, v in result.items() if k != 'calls'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('build')
    for name in ('source', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p = commands.add_parser('run')
    for name in ('candidate', 'installed', 'fixture', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--pin', required=True)
    p.add_argument('--limit', type=int, default=4)
    args = vars(parser.parse_args())
    command = args.pop('command')
    os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    print(json.dumps({'build': build, 'run': run}[command](**args)))
