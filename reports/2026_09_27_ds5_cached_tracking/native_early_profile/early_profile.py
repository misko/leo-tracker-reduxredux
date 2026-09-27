"""Isolate early-symbol native scoring; not a qualified detector replacement."""
import ctypes as ct
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import leo
assert Path(leo.__file__).resolve() == ROOT / 'src/leo/__init__.py'
sys.path.insert(0, str(HERE.parent / 'native_guided_boundary'))
import native_guided_boundary as base


def sources():
    return base._sources() + [Path(__file__).resolve(),
        ROOT / 'src/leo/analysis/starlink/templates.py',
        ROOT / 'src/leo/analysis/starlink/pilot_methods.py']


def verify(path):
    receipt = json.loads(path.with_suffix('.build.json').read_text())
    assert receipt['symbol_diversity'] == 0
    assert receipt['binary_sha256'] == base.sha256(path)
    assert receipt['sources'] == {str(p): base.sha256(p) for p in sources()}
    return receipt


def build():
    path = HERE / 'libearly_local.so'
    if path.exists():
        verify(path)
        return path
    assert not path.with_suffix('.build.json').exists()
    flags = json.loads((base.RESEARCH_NATIVE / 'profile.json').read_text())['flags']
    assert flags.count('-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1') == 1
    flags = [f.replace('GLRT_SYMBOL_DIVERSITY=1', 'GLRT_SYMBOL_DIVERSITY=0') for f in flags]
    hashes = {str(p): base.sha256(p) for p in sources()}
    compiler = shutil.which('cc')
    assert compiler
    command = [compiler, '-std=c11', '-O3', '-fno-math-errno', '-Wall', '-Wextra',
               '-Werror', *flags, '-shared', '-fPIC']
    for directory in (base.HERE, base.TG11, base.RESEARCH_NATIVE, base.DEPLOY_NATIVE):
        command += ['-I', str(directory)]
    command += [str(base.HERE / 'guided_boundary_native.c'),
                str(base.FFT32 / 'fft32_fftw.c'),
                '/usr/lib/x86_64-linux-gnu/libfftw3f.so.3', '-lm', '-o', str(path)]
    subprocess.run(command, check=True)
    assert hashes == {str(p): base.sha256(p) for p in sources()}
    with path.with_suffix('.build.json').open('x') as stream:
        json.dump({'symbol_diversity': 0, 'sources': hashes, 'command': command,
                   'compiler_sha256': base.sha256(Path(compiler).resolve()),
                   'binary_sha256': base.sha256(path)}, stream, indent=2)
    verify(path)
    return path


class NativeEarly(base.NativeTG11):
    def __init__(self, rate, edge):
        super().__init__(rate, edge, library=build())
        self.library.leo_tg11_guided_support_guard_hz.restype = ct.c_double
        assert self.library.leo_tg11_guided_support_guard_hz() == base.SUPPORT_GUARD_HZ
