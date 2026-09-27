"""Build a separate numerical experiment using the frozen V4 common profile."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'native/libblind_strided_v4.so.build.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    base = json.loads(BASE.read_text())
    for name, expected in base['sources_sha256'].items():
        if digest(name) != expected:
            raise ValueError('parent build source drift')
    binary = HERE / 'libfft32.so'
    receipt = binary.with_suffix('.so.build.json')
    sources = dict(base['sources_sha256'])
    # Remove the original FFT implementation, retain its common ABI header.
    original = next(name for name in sources if name.endswith('/fft.c'))
    del sources[original]
    sources.update({str(p): digest(p) for p in (HERE / 'fft32.c', Path(__file__))})
    if binary.exists() or receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved['sources_sha256'] != sources or digest(binary) != saved['binary_sha256']:
            raise ValueError('refuse to reuse changed numerical experiment')
        return binary
    command = [str(HERE / 'fft32.c') if arg == original else arg for arg in base['command']]
    command[command.index('-o') + 1] = str(binary)
    subprocess.run(command, check=True)
    for name, expected in sources.items():
        if digest(name) != expected:
            raise ValueError('source changed during build')
    result = {'schema': 'org.leo.research.fft32-build/v1', 'command': command,
              'sources_sha256': sources, 'binary_sha256': digest(binary),
              'parent_receipt_sha256': digest(BASE),
              'compiler_sha256': digest(command[0]),
              'semantics': 'FP32 all FFTs; unchanged FP64 outer detector; not bit-equivalent'}
    with receipt.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return binary


if __name__ == '__main__':
    print(build())
