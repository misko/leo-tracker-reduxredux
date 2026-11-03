"""Isolate hash-bound research incumbents for paired numerical reconstruction.

This is not a public production terminal or a complete reassociation replay.
The historical research exports already contain native observations and orbits.
"""

import argparse
import json
import re
import shutil
from pathlib import Path

from algo06_cache import relocate

from leo.cli.algo07_profile import destination, digest, freeze, write_new

RESEARCH = Path('/srv/bulk/leo/research')


def proof_closure(sources):
    """Follow explicit digest edges, including historical receipts outside a case root."""
    pending = list(sources)
    sources = set(sources)

    def require(path, expected):
        if not path.is_absolute() or not path.is_relative_to(RESEARCH):
            return
        if path.is_symlink() or not path.resolve().is_relative_to(RESEARCH):
            raise ValueError('Research proof escapes private exports')
        if digest(path) != expected.removeprefix('sha256:'):
            raise ValueError('Research proof digest mismatch: ' + str(path))
        if path not in sources:
            sources.add(path)
            pending.append(path)

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if (isinstance(item, str) and re.fullmatch(r'(sha256:)?[0-9a-f]{64}', item)
                        and key.startswith('/')):
                    require(Path(key), item)
                else:
                    visit(item)
            if isinstance(value.get('root'), str) and isinstance(value.get('files'), dict):
                for name, expected in value['files'].items():
                    if (isinstance(expected, str)
                            and re.fullmatch(r'(sha256:)?[0-9a-f]{64}', expected)):
                        require(Path(value['root']) / name, expected)

    while pending:
        path = pending.pop()
        if len(sources) > 20000:
            raise ValueError('Research proof closure exceeds bounded snapshot size')
        if path.suffix == '.json':
            visit(json.loads(path.read_text()))
    return sources


def prepare(manifest, case, output, reference_kernel):
    output = destination(output)
    rows = json.loads(manifest.read_text())['files']
    bound = {r['path']: r for r in rows}

    def frozen(path):
        row = bound.get(str(path))
        if row is None or digest(path) != row['sha256']:
            raise ValueError('Research top-level input is not the frozen reference: ' + str(path))
        return json.loads(path.read_text())

    match = [Path(r['path']) for r in rows if r.get('case') == case
             and Path(r['path']).parent.name == 'inputs']
    if len(match) != 1:
        raise ValueError('Exactly one frozen research case required')
    original = match[0]
    cohort = original.parents[1]
    z = frozen(original)
    position = frozen(cohort / 'position' / case / 'result.json')
    catalogue = frozen(cohort / 'catalogues' / (case + '.json'))
    # Capture the two existing exported contexts, without touching original files.
    native = Path(z['native_path'])
    if native.parts[-3:-1] != ('snapshot', 'inference'):
        raise ValueError('Expected the existing native snapshot layout')
    roots = [Path(z['recovery_path']), native.parents[2]]
    roots = [r for r in roots if not any(r != q and r.is_relative_to(q) for q in roots)]
    if any(not r.resolve().is_relative_to(RESEARCH) for r in roots):
        raise ValueError('Expected existing private research exports')
    sources = {p for r in roots for p in r.rglob('*') if p.is_file()}
    sources.add(Path(z['baseline_source']))
    sources = proof_closure(sources)
    if any(p.is_symlink() or not p.resolve().is_relative_to(RESEARCH) for p in sources):
        raise ValueError('Research input escapes the exported contexts')
    if any(output.is_relative_to(r) or r.is_relative_to(output) for r in roots):
        raise ValueError('Snapshot overlaps reference')
    output.mkdir(parents=True, exist_ok=False)
    stage = output / 'original'
    stage.mkdir()
    files = {}
    for source in sorted(sources):
        name = str(source.relative_to(RESEARCH))
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(source)
        shutil.copyfile(source, target)
        if digest(target) != before or digest(source) != before:
            raise ValueError('Research export changed while copying')
        files[name] = before
    for name, value in [('inputs/SCAN.json', dict(z, case='SCAN')),
                        ('position/SCAN/result.json', position),
                        ('catalogues/SCAN.json', catalogue)]:
        write_new(stage / name, value)
        files[name] = digest(stage / name)
    # A qualified ALGO06 addition needs its frozen causal nomination receipt.
    if position['decisions']['72h_30s']['status'] == 'qualified':
        screen = cohort / 'screen' / case / 'result.json'
        # This receipt is transitive evidence, newly hash-bound before replay.
        payload = screen.read_bytes()
        target = stage / 'screen/SCAN/result.json'
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        if screen.read_bytes() != payload:
            raise ValueError('Research screen changed while copying')
        files['screen/SCAN/result.json'] = digest(target)
    receipt = relocate(stage, output / 'input', RESEARCH, files)
    shutil.copyfile(reference_kernel, output / 'reference_kernel.py')
    metadata = dict(case=case, research_only=True, complete_reassociation_supported=False,
                    source_manifest=str(manifest), source_manifest_sha256=digest(manifest),
                    relocation=receipt, top_level_paths=list(map(str, (
                        original, cohort/'position'/case/'result.json',
                        cohort/'catalogues'/(case+'.json')))))
    write_new(output / 'source.json', metadata)
    entries = [dict(path=str(output / 'input' / name), sha256=sha)
               for name, sha in receipt['relocated_hashes'].items()]
    entries.append(dict(path=str(output/'reference_kernel.py'), sha256=digest(reference_kernel)))
    write_new(output/'spec.json', dict(files=entries, metadata=dict(case=case, research_only=True)))
    freeze(output/'spec.json', output/'frozen.json')
    print(json.dumps(dict(case=case, files=len(entries), output=str(output))), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reference-kernel', type=Path, required=True)
    a = p.parse_args()
    prepare(a.manifest.resolve(), a.case, a.output.resolve(), a.reference_kernel.resolve())
