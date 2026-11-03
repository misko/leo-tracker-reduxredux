"""Build a research-only FP32 coarse screen; this is not an exact GLRT runtime."""

import argparse
import json
import shlex
import shutil
import subprocess
import sysconfig
from pathlib import Path

from stage_native_glrt_runtime import digest, verify, verify_files


def transform(source, grid):
    marker = 'if (kernel->cfo_count == 12) {'
    if grid.count(marker) != 1 or source.count('cfo_count == 12') != 1:
        raise ValueError('Unknown native register layout')
    start = grid.index(marker)
    end = grid.index('} else {', start)
    branch = grid[start:end].replace('cfo_count == 12', 'cfo_count == 24')
    branch = branch.replace('__m256d', '__m256').replace('_pd(', '_ps(')
    branch = branch.replace('index * 12', 'index * 24')
    branch = branch.replace('rotated_base + 8', 'rotated_base + 16')
    branch = branch.replace('rotated_base + 4', 'rotated_base + 8')
    store_start = branch.index('                    _mm256_storeu_ps(correlation_real,')
    branch = branch[:store_start] + '''                    float real32[24], imag32[24];
                    _mm256_storeu_ps(real32, correlation_real_0);
                    _mm256_storeu_ps(real32 + 8, correlation_real_1);
                    _mm256_storeu_ps(real32 + 16, correlation_real_2);
                    _mm256_storeu_ps(imag32, correlation_imag_0);
                    _mm256_storeu_ps(imag32 + 8, correlation_imag_1);
                    _mm256_storeu_ps(imag32 + 16, correlation_imag_2);
                    for (int f = 0; f < 24; ++f) {
                        correlation_real[f] = real32[f];
                        correlation_imag[f] = imag32[f];
                    }
                '''
    grid = grid[:start] + branch + grid[end:]
    declarations = '''    double *restrict rotated_real = kernel->rotated_real;
    double *restrict rotated_imag = kernel->rotated_imag;'''
    if grid.count(declarations) != 1:
        raise ValueError('Unknown rotated-reference layout')
    grid = grid.replace(declarations, '''#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)
    npy_intp maximum_taps = 0;
    for (npy_intp s = 0; s < kernel->symbol_count; ++s) {
        npy_intp taps = stops[s] - starts[s];
        if (taps > maximum_taps) maximum_taps = taps;
    }
    float *restrict rotated_real = malloc(maximum_taps * kernel->cfo_count * sizeof(float));
    float *restrict rotated_imag = malloc(maximum_taps * kernel->cfo_count * sizeof(float));
    if (rotated_real == NULL || rotated_imag == NULL) {
        free(rotated_real);
        free(rotated_imag);
        kernel->invalid_geometry = 1;
        return;
    }
#else
    double *restrict rotated_real = kernel->rotated_real;
    double *restrict rotated_imag = kernel->rotated_imag;
#endif''')
    ending = '    kernel->invalid_geometry = invalid_geometry;'
    if grid.count(ending) != 1:
        raise ValueError('Unknown grid termination')
    grid = grid.replace(ending, '''#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)
    free(rotated_real);
    free(rotated_imag);
#endif
''' + ending)
    source = source.replace('cfo_count == 12', 'cfo_count == 24')
    source = source.replace('#include <math.h>', '#include <math.h>\n#include <stdlib.h>')
    return source, grid


def build(base, pin, output, *, integer=False):
    import numpy

    base, output = base.resolve(strict=True), output.resolve()
    if output.exists() or not output.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research directory required')
    manifest = verify(base, pin)
    inventory = manifest['files_sha256']
    prefix = 'src/leo/analysis/starlink/'
    names = [prefix + name for name in ('_native_acquisition.c', '_native_acquisition_grid.inc')]
    selected_transform = transform
    if integer:
        from native_integer_screen import transform as selected_transform
    texts = selected_transform(*[(base / name).read_text() for name in names])
    output.mkdir(parents=True)
    for name in inventory:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / name, destination)
    for name, text in zip(names, texts, strict=True):
        (output / name).write_text(text)
    extension = prefix + '_native_acquisition' + sysconfig.get_config_var('EXT_SUFFIX')
    command = [*shlex.split(sysconfig.get_config_var('CC')), '-shared', '-fPIC', '-O3',
               '-fno-math-errno', '-Wall', '-Wextra',
               '-I' + sysconfig.get_path('include'), '-I' + numpy.get_include(),
               str(output / names[0]), str(output / prefix / 'fast_scan_fold.c'),
               '-lm', '-o', str(output / extension)]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    candidate = {name: digest(output / name) for name in inventory}
    changed = sorted(name for name in inventory if inventory[name] != candidate[name])
    if changed != sorted(names + [extension]):
        raise ValueError('Unexpected source or binary changes')
    verify(base, pin)
    verify_files(output, candidate)
    receipt = dict(base=str(base), base_pin=pin, candidate=str(output),
                   files_sha256=candidate, changes=changed, compile_command=command,
                   compiler=subprocess.check_output(command[:1] + ['--version'], text=True),
                   compiler_stderr=completed.stderr, builder_sha256=digest(Path(__file__)),
                   production_modified=False, qualification='approximate screening research only',
                   safe_for_inference=False, error_bounds_implemented=False,
                   exact_rescoring_implemented=False)
    receipt['screen_kind'] = 'integer_vnni' if integer else 'fp32'
    if integer:
        receipt['transformer_sha256'] = digest(Path(__file__).with_name('native_integer_screen.py'))
    (output / 'screen-probe.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return dict(candidate=str(output), changed=changed, safe_for_inference=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--pin', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--integer', action='store_true', help='Research integer-IQ VNNI screen')
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.pin, args.output, integer=args.integer)))
