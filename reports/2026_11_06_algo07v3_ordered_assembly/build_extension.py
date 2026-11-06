"""Build the owned extension with the measured strict flags in the pinned environment.

Normal wheel builds use setup.py. This local build avoids changing the frozen
environment when its runtime-only installation does not contain setuptools.
"""

import argparse
import hashlib
import json
import subprocess
import sysconfig
from pathlib import Path

import numpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError('Fresh receipt required')
    source = Path('src/leo/analysis/_ordered_assembly.c')
    output = source.with_name('_ordered_assembly' + sysconfig.get_config_var('EXT_SUFFIX'))
    command = ['cc', '-O3', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra',
               '-Werror', '-shared', '-fPIC', '-I' + sysconfig.get_path('include'),
               '-I' + numpy.get_include(), str(source), '-o', str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    receipt = dict(command=command, returncode=result.returncode,
                   stdout=result.stdout, stderr=result.stderr,
                   compiler=subprocess.check_output(['cc', '--version'], text=True),
                   sources={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            (source, source.with_name('_ordered_scatter.c'), Path('setup.py'))})
    if result.returncode == 0:
        receipt['binary_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    result.check_returncode()


if __name__ == '__main__':
    main()
