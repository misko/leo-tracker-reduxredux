"""Direct-extension ablation of the external ordered-assembly experiment."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sysconfig
from pathlib import Path

import numpy as np
import probe_algo07v3_ordered_assembly as harness


def build(root):
    source = Path(__file__).with_name('algo07v3_ordered_scatter_module.c')
    library = root / ('_algo07v3_ordered_scatter' + sysconfig.get_config_var('EXT_SUFFIX'))
    command = ['cc', '-O3', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra',
               '-Werror', '-shared', '-fPIC', '-I' + sysconfig.get_path('include'),
               '-I' + np.get_include(), str(source), '-o', str(library)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    metadata = dict(command=command, compiler=subprocess.check_output(['cc', '--version'], text=True),
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    binary_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    (root / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    spec = importlib.util.spec_from_file_location('_algo07v3_ordered_scatter', library)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scatter


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output', type=Path, required=True)
    args, _ = parser.parse_known_args()
    paths = [Path(__file__), Path(__file__).with_name('algo07v3_ordered_scatter_module.c')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    original = harness.build
    try:
        harness.build = build
        harness.main()
    finally:
        harness.build = original
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    path = args.output / 'result.json'
    result = json.loads(path.read_bytes())
    result['bindings'].update(bindings)
    result['backend'] = 'direct_extension'
    path.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
