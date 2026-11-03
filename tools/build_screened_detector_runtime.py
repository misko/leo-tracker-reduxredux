"""Compose a research detector with separate FP32 screen and original FP64 oracle."""

import argparse
import ast
import json
import shutil
from pathlib import Path

from stage_native_glrt_runtime import digest, verify, verify_files


def transform(source):
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef) and n.name == 'acquire_symbolwise']
    if len(nodes) != 1:
        raise ValueError('Unknown acquisition layout')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    block = ''.join(lines[node.lineno-1:node.end_lineno])
    begin = '    coarse_scores = _folded_anchor_score_grid(\n'
    end = '    if not retained or retained[0][0] <= 0:\n'
    if (block.count(begin) != 1 or block.count(end) != 1
            or block.count('    retained = _retain_score_map_peaks(') != 1):
        raise ValueError('Unknown complete-grid selection layout')
    start, stop = block.index(begin), block.index(end)
    replacement = '''    from .coarse_screen import acquire as _screened_acquire
    import sys

    coarse_scores, retained = _screened_acquire(
        sys.modules[__name__],
        (values, exact, sample_rate_hz, coarse_absolute, config.anchor_symbols, epoch_count),
        coarse_residuals, config.retained_candidate_count,
        config.candidate_epoch_separation_samples, config.candidate_cfo_separation_hz,
    )
    for residual, scores in zip(coarse_residuals, coarse_scores, strict=True):
        score_maps[residual] = scores
'''
    block = block[:start] + replacement + block[stop:]
    lines[node.lineno-1:node.end_lineno] = [block]
    return ''.join(lines)


def build(repo, screen, output):
    repo, screen, output = repo.resolve(strict=True), screen.resolve(strict=True), output.resolve()
    if output.exists() or not output.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research directory required')
    screen_receipt = screen / 'screen-probe.json'
    screen_pin = digest(screen_receipt)
    prototype = json.loads(screen_receipt.read_text())
    base = Path(prototype['base'])
    manifest = verify(base, prototype['base_pin'])
    verify_files(screen, prototype['files_sha256'])
    prefix = 'src/leo/analysis/starlink/'
    pairs = [('native_exact_columns.py', '_screen_exact.py'),
             ('native_screen_bounds.py', '_screen_bounds.py'),
             ('interval_coarse_selection.py', '_screen_selection.py')]
    for tool, module in pairs:
        if (repo / 'tools' / tool).read_bytes() != (repo / prefix / module).read_bytes():
            raise ValueError('Qualified research helper and component copy differ: ' + module)
    output.mkdir(parents=True)
    for name in manifest['files_sha256']:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / name, destination)
    acquisition = prefix + 'acquisition.py'
    (output / acquisition).write_text(transform((base / acquisition).read_text()))
    added = []
    for name in ['coarse_screen.py', *[p[1] for p in pairs]]:
        member = prefix + name
        shutil.copyfile(repo / member, output / member)
        added.append(member)
    native_directory = output / prefix / '_screen_native'
    native_directory.mkdir()
    (native_directory / '__init__.py').write_text(
        '"""Research-only approximate native kernel."""\n')
    added.append(prefix + '_screen_native/__init__.py')
    native_members = [prefix + '_native_acquisition.c', prefix + '_native_acquisition_grid.inc']
    native_members += [name for name in prototype['files_sha256']
                       if name.startswith(prefix + '_native_acquisition.') and name.endswith('.so')]
    if len(native_members) != 3:
        raise ValueError('Ambiguous native screen extension')
    for member in native_members:
        name = prefix + '_screen_native/' + Path(member).name
        shutil.copyfile(screen / member, output / name)
        added.append(name)
    inventory = {name: digest(output / name) for name in [*manifest['files_sha256'], *added]}
    changed = [name for name in manifest['files_sha256']
               if manifest['files_sha256'][name] != inventory[name]]
    if changed != [acquisition]:
        raise ValueError('Unexpected deployed member changes')
    verify(base, prototype['base_pin'])
    verify_files(screen, prototype['files_sha256'])
    verify_files(output, inventory)
    if digest(screen_receipt) != screen_pin:
        raise ValueError('Screen source changed during composition')
    receipt = dict(base=str(base), base_pin=prototype['base_pin'], candidate=str(output),
                   screen=str(screen), screen_receipt_sha256=screen_pin,
                   files_sha256=inventory, changes=changed, additions=added,
                   component_sources={n: digest(repo / n) for n in added
                                      if '/_screen_native/' not in n},
                   builder_sha256=digest(Path(__file__)), production_modified=False,
                   qualification='isolated detector qualification; not installed')
    (output / 'screened-detector.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return dict(candidate=str(output), changed=changed, additions=len(added))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--screen', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repo, args.screen, args.output)))
