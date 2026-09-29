#!/usr/bin/env python3
"""Build immutable Cortex-A9 Thumb-2 and O2 code-generation points."""
import hashlib, json, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'sources'
CC = '/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
INC = '/var/tmp/leo-fftw-float-20260912/install/include'
FFTW = '/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
THRESHOLDS = {'2500000': .312, '5000000': .150, '7500000': .175, '10000000': .152}
UNITS = [('test_rank_histograms.c', 'test_rank_histograms'),
         ('test_dwell_input.c', 'test_dwell_input'),
         ('test_fused_fold.c', 'test_fused_fold'),
         ('test_rank_radix11.c', 'test_rank_radix11'),
         ('test_direct_ci16_ingest.c', 'test_direct_ci16_ingest'),
         ('test_sparse_peak_scan.c', 'test_sparse_peak_scan'),
         ('test_rate_coarse_gate.c', 'test_rate_coarse_gate'),
         ('test_final_reuse.c', 'test_final_reuse'),
         ('test_fine_precision.c', 'test_fine_budget'),
         ('test_moment_accuracy.c', 'test_moment_accuracy')]

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def invoke(command):
    p = subprocess.run(command, text=True, capture_output=True, check=True)
    return {'command': command, 'stdout': p.stdout, 'stderr': p.stderr}

def command(out, sources, name, variant, budget=2):
    optimization = '-O2' if variant == 'o2' else '-O3'
    flags = ['-DCONDITIONED_MOMENT_BLOCK=64', '-DLEO_PRESENCE_FFTW=1',
             '-DLEO_PROPOSAL_LIBRARY', '-DLEO_PROPOSAL_OMIT_POWER=1',
             '-DLEO_NEON_CONDITIONED_MOMENTS=1', '-std=c11', optimization,
             '-Wall', '-Wextra', '-Werror', '-Wno-error=lto-type-mismatch',
             '-fno-fast-math', '-flto', '-fno-math-errno',
             '-fno-trapping-math', '-fcx-limited-range',
             f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}',
             '-DSKIP_CONDITIONED_RECHECK=1',
             '-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1',
             '-DLEO_PRESENCE_COARSE_FRAMES=16', '-DLEO_PRESENCE_COARSE_FP32',
             '-DLEO_FULL_CONDITIONED_SCREEN', '-DLEO_FULL_REFINEMENT_MODE=2',
             '-mcpu=cortex-a9', '-mfpu=neon', '-mfloat-abi=hard',
             '-DLEO_FULL_ARM_AFFINITY', '-DLEO_PROPOSAL_NEON_FOLD', f'-I{INC}']
    if variant == 'thumb': flags.append('-mthumb')
    return [CC, *flags, '-I', str(out/'src/native_presence'), '-I', str(out),
            *[str(out/s) for s in sources], str(out/'conditioned_czt.c'),
            str(out/'fft_full.c'), FFTW, '-lfftw3', '-lm', '-o', str(out/name)]

def build(variant):
    out = ROOT / ('builds-' + variant)
    if out.exists(): raise SystemExit(f'{out} already exists; artifacts are immutable')
    shutil.copytree(SOURCE, out)
    commands = []
    binary = f'fused_wave7_hist_{variant}_arm'
    link = command(out, ['fused_probe.c', 'proposal_core.c'], binary, variant)
    core, obj = str(out/'proposal_core.c'), str(out/'proposal_core.o')
    prefix = link[:link.index('-I')]
    commands.append(invoke([*prefix, '-fno-lto', '-c', core, '-o', obj]))
    link[link.index(core)] = obj
    commands.append(invoke(link))
    binaries = [out/binary]
    for source, stem in UNITS:
        name = f'{stem}_{variant}_arm'
        commands.append(invoke(command(out, [source], name, variant, 0)))
        binaries.append(out/name)
    receipt = {
        'schema': 'arm-wave7-codegen-matrix-build/v1', 'variant': variant,
        'codegen_delta': '-mthumb at O3' if variant == 'thumb' else '-O2 replacing -O3',
        'coarse_score_thresholds': THRESHOLDS,
        'scientific_flags_unchanged': True,
        'selection': 'Wave7 exact one-scan integer-key histogram ranker',
        'commands': commands,
        'binaries': {p.name: sha(p) for p in binaries},
        'sources': {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
                    if p.is_file() and p.suffix in ('.c', '.h')},
    }
    (out/'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return {'receipt': str((out/'build-receipt.json').relative_to(ROOT)),
            'receipt_sha256': sha(out/'build-receipt.json'),
            'binary_sha256': sha(out/binary)}

if __name__ == '__main__':
    result = {variant: build(variant) for variant in ('thumb', 'o2')}
    (ROOT/'build-manifest.json').write_text(json.dumps(result, indent=2)+'\n')
