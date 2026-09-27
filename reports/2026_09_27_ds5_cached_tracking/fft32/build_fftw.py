"""Pin the installed server FFTW-float implementation for this experiment."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    parent = HERE.parent / 'native/libblind_strided_v4.so.build.json'
    base = json.loads(parent.read_text())
    for name, expected in base['sources_sha256'].items():
        if digest(name) != expected:
            raise ValueError('parent source drift')
    original = next(name for name in base['sources_sha256'] if name.endswith('/fft.c'))
    sources = {n: h for n, h in base['sources_sha256'].items() if n != original}
    dependency = Path('/usr/lib/x86_64-linux-gnu/libfftw3f.so.3').resolve()
    sources.update({str(p): digest(p) for p in
                    (HERE / 'fft32_fftw.c', Path(__file__), Path('/usr/include/fftw3.h'),
                     dependency)})
    binary = HERE / 'libfft32_fftw.so'
    receipt = binary.with_suffix('.so.build.json')
    if binary.exists() or receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved['sources_sha256'] != sources or saved['binary_sha256'] != digest(binary):
            raise ValueError('changed FFTW experiment')
        return binary
    command = [str(HERE / 'fft32_fftw.c') if arg == original else arg for arg in base['command']]
    command[command.index('-o') + 1] = str(binary)
    command.insert(command.index('-lm'), str(dependency))
    subprocess.run(command, check=True)
    for name, expected in sources.items():
        if digest(name) != expected:
            raise ValueError('source/dependency changed during build')
    result = {'schema': 'org.leo.research.fft32-fftw-build/v1', 'command': command,
              'sources_sha256': sources, 'binary_sha256': digest(binary),
              'parent_receipt_sha256': digest(parent),
              'compiler_sha256': digest(command[0]),
              'semantics': 'FP32 FFTW all FFTs, ESTIMATE plans; not bit-equivalent'}
    with receipt.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return binary


if __name__ == '__main__':
    print(build())
