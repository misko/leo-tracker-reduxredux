"""Build isolated scheduling-only native probes; never install them."""

import argparse
import json
import shlex
import shutil
import subprocess
import sysconfig
from pathlib import Path

from stage_native_glrt_runtime import digest, verify, verify_files


def transform(source):
    old = 'target("avx2,fma,tune=haswell")'
    if source.count(old) != 2:
        raise ValueError("Unknown native target layout")
    return source.replace(old, 'target("avx2,fma,tune=arrowlake")')


def build(base, pin, output, *, unroll=False):
    import numpy

    base, output = base.resolve(strict=True), output.resolve()
    if output.exists() or not output.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError("New private research directory required")
    manifest = verify(base, pin)
    inventory = manifest['files_sha256']
    prefix = 'src/leo/analysis/starlink/'
    member = prefix + '_native_acquisition.c'
    candidate_source = transform((base / member).read_text())
    output.mkdir(parents=True)
    for name in inventory:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / name, destination)
    (output / member).write_text(candidate_source)
    extension = prefix + '_native_acquisition' + sysconfig.get_config_var('EXT_SUFFIX')
    command = [*shlex.split(sysconfig.get_config_var('CC')), '-shared', '-fPIC', '-O3',
               '-fno-math-errno', '-Wall', '-Wextra',
               *(['-funroll-loops'] if unroll else []),
               '-I' + sysconfig.get_path('include'), '-I' + numpy.get_include(),
               str(output / member), str(output / prefix / 'fast_scan_fold.c'),
               '-lm', '-o', str(output / extension)]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    candidate = {name: digest(output / name) for name in inventory}
    changed = sorted(name for name in inventory if inventory[name] != candidate[name])
    if changed != sorted([member, extension]):
        raise ValueError("Unexpected source or binary changes")
    verify(base, pin)
    verify_files(output, candidate)
    receipt = dict(base=str(base), base_pin=pin, candidate=str(output),
                   files_sha256=candidate, changes=changed, compile_command=command,
                   compiler=subprocess.check_output(command[:1] + ['--version'], text=True),
                   compiler_stderr=completed.stderr, builder_sha256=digest(Path(__file__)),
                   unroll=unroll, tune='arrowlake', isa='avx2,fma',
                   production_modified=False, qualification='research only')
    (output / 'schedule-probe.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return dict(candidate=str(output), unroll=unroll, changed=changed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--pin', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unroll', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.pin, args.output, unroll=args.unroll)))
