"""Stage a lean report; keep bulky numerical archives external and hash-bound."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
REPORT = Path('reports/2026_10_25_ds24_ambiguity_position')
EXCLUDED_PARTS = {'publication', '__pycache__', '.pytest_cache'}
EXCLUDED_NAMES = {'publication_receipt.json', 'publication_checks.json'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for name in ('README.md', 'REPLAY.md', 'ambiguity/FINDINGS.md', 'inventory/FINDINGS.md'):
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    # Actual independent terminal receipts must be named explicitly at finalization.
    terminal = json.loads((ROOT / 'terminal_checks.json').read_text())
    if terminal.get('all_passed') is not True:
        raise ValueError('independent terminal checks are not complete')
    for item in terminal['audits']:
        path = Path(item['path'])
        if sha(path) != item['sha256'] or not json.loads(path.read_text()).get('all_passed'):
            raise ValueError('terminal audit differs: ' + str(path))
    inventory_manifest = ROOT / 'inventory/lean_publication.json'
    inventory_files = json.loads(inventory_manifest.read_text())['files']
    for name, expected in inventory_files.items():
        if sha(Path(name)) != expected:
            raise ValueError('inventory publication file differs: ' + name)
    stage = ROOT / 'publication'
    stage.mkdir(exist_ok=False)
    included, external = {}, {}
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if not path.is_file() or EXCLUDED_PARTS.intersection(rel.parts) or path.name in EXCLUDED_NAMES:
            continue
        record = dict(source=str(path), bytes=path.stat().st_size, sha256=sha(path))
        # Figures, complete tables, sources and prose are self-contained in Git.
        # Large results, ownership lists and design arrays remain local with hashes.
        bulky = (('inventory' == rel.parts[0] and
                  str(path) not in inventory_files and path != inventory_manifest) or
                 path.suffix == '.npz' or
                 bool({'ownership', 'arrays', 'prepared'}.intersection(rel.parts)) or
                 path.name in {'inventory.json', 'metadata.json', 'execution.json'} or
                 (path.stat().st_size > 1024**2 and
                  path.suffix not in {'.png', '.pdf', '.svg', '.csv', '.md', '.py'}))
        if bulky:
            external[str(rel)] = record
            continue
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        if sha(dst) != record['sha256']:
            raise ValueError('copy mismatch: ' + str(rel))
        included[str(rel)] = record
    manifest = dict(included=included, external=external, report=str(REPORT),
                    external_arrays_not_standalone_reproducible=True,
                    source_bytes_unchanged=True, no_scientific_execution=True)
    (stage / 'publication_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    checked, missing = [], []
    for path in stage.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            target = target.strip().strip('<>').split('#', 1)[0]
            if not target or target.startswith(('http:', 'https:', 'mailto:', '/')):
                continue
            resolved = (path.parent / target).resolve()
            record = dict(file=str(path.relative_to(stage)), target=target)
            if resolved.is_file():
                checked.append(record)
                continue
            # External numerical archives must be explicitly linked as absolute
            # source paths in prose; do not publish silently broken relative links.
            final = (PUBLISHER / REPORT / path.relative_to(stage).parent / target).resolve()
            try:
                relative = final.relative_to(PUBLISHER)
                result = subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + str(relative)],
                                        cwd=PUBLISHER, capture_output=True)
            except ValueError:
                result = None
            if result is not None and result.returncode == 0:
                checked.append(record)
            else:
                missing.append(record)
    checks = dict(files=len(included) + 1, bytes=sum(x['bytes'] for x in included.values()),
                  external_files=len(external), checked_relative_links=checked,
                  missing_links=missing, ready=not missing,
                  manifest_sha256=sha(stage / 'publication_manifest.json'))
    (ROOT / 'publication_checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps({k: v for k, v in checks.items() if k != 'checked_relative_links'}))
    if missing:
        raise ValueError('relative report links require correction before commit')


if __name__ == '__main__':
    main()
