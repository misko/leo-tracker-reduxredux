"""Build an isolated native CFO-tiling candidate; never alter installed code."""

import argparse
import ast
import hashlib
import json
import shlex
import shutil
import subprocess
import sysconfig
from pathlib import Path

import numpy


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_function(original, candidate, name):
    def node(text):
        matches = [n for n in ast.parse(text).body
                   if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(matches) != 1:
            raise ValueError('Expected exactly one named function')
        return matches[0]
    old, new = node(original), node(candidate)
    lines = original.splitlines(keepends=True)
    lines[old.lineno-1:old.end_lineno] = candidate.splitlines(keepends=True)[
        new.lineno-1:new.end_lineno]
    return ''.join(lines)


def build(base, repo, output):
    base, repo = base.resolve(strict=True), repo.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to('/mnt/qnap01') or output.exists():
        raise ValueError('New isolated output required')
    prefix = Path('src/leo/analysis/starlink')
    original = {str(p.relative_to(base)): digest(p) for p in base.rglob('*')
                if p.is_file() and '__pycache__' not in p.parts}
    shutil.copytree(base, output, ignore=shutil.ignore_patterns('__pycache__'))
    target = output/prefix
    acquisition = target/'acquisition.py'
    acquisition.write_text(replace_function(
        acquisition.read_text(), (repo/prefix/'acquisition.py').read_text(),
        '_folded_anchor_score_grid_native'))
    for name in ('_native_acquisition.c', '_native_acquisition_grid.inc'):
        shutil.copyfile(repo/prefix/name, target/name)
    extension = target/('_native_acquisition'+sysconfig.get_config_var('EXT_SUFFIX'))
    command = [*shlex.split(sysconfig.get_config_var('CC')), '-shared', '-fPIC',
               '-O3', '-fno-math-errno', '-Wall', '-Wextra',
               '-I'+sysconfig.get_path('include'), '-I'+numpy.get_include(),
               str(target/'_native_acquisition.c'), str(target/'fast_scan_fold.c'),
               '-lm', '-o', str(extension)]
    subprocess.run(command, check=True)
    candidate = {str(p.relative_to(output)): digest(p) for p in output.rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts}
    differences = [name for name in sorted(set(original) | set(candidate))
                   if original.get(name) != candidate.get(name)]
    expected = [str(prefix/name) for name in (
        'acquisition.py', '_native_acquisition.c', '_native_acquisition_grid.inc',
        extension.name)]
    if set(differences) != set(expected):
        raise ValueError('Unexpected prototype changes: '+repr(differences))
    for name, expected_sha in original.items():
        if digest(base/name) != expected_sha:
            raise ValueError('Installed source changed during build')
    receipt = dict(base=str(base), candidate=str(output), compile_command=command,
                   compiler=subprocess.check_output(command[:1]+['--version'], text=True),
                   changes=differences, original_sha256=original,
                   candidate_sha256=candidate, production_modified=False)
    (output/'prototype-build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.base, args.repo, args.output)
    print(json.dumps(dict(changes=result['changes'], production_modified=False)))
