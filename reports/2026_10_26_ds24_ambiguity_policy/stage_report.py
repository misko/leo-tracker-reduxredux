"""Publish compact evidence without copying the external corpus or numerical banks."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
REPORT = Path('reports/2026_10_26_ds24_ambiguity_policy')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for name in ('README.md', 'REPLAY.md', 'REPLAY_FINDINGS.md',
                 'position/FINDINGS.md', 'qualification/FINDINGS.md'):
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    terminal = json.loads((ROOT / 'terminal_checks.json').read_text())
    if terminal.get('all_passed') is not True:
        raise ValueError('Terminal checks incomplete')
    for item in terminal['audits']:
        path = Path(item['path'])
        if sha(path) != item['sha256'] or not json.loads(path.read_text()).get('all_passed'):
            raise ValueError('Terminal audit differs: ' + str(path))
    qualification_manifest = ROOT / 'qualification/lean_publication.json'
    qualification = json.loads(qualification_manifest.read_text())['published']
    qualification_files = {item['path']: item['sha256'] for item in qualification}
    for name, digest in qualification_files.items():
        if sha(Path(name)) != digest:
            raise ValueError('Qualification publication file differs: ' + name)
    stage = ROOT / 'publication'
    stage.mkdir(exist_ok=False)
    included, external = {}, {}
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if (not path.is_file() or {'publication', '__pycache__', '.pytest_cache'}.intersection(rel.parts)
                or path.name in {'publication_receipt.json', 'publication_checks.json'}):
            continue
        record = dict(source=str(path), bytes=path.stat().st_size, sha256=sha(path))
        bulky = ((rel.parts[0] == 'qualification' and
                  str(path) not in qualification_files and path != qualification_manifest) or
                 path.suffix == '.npz' or
                 bool({'arrays', 'prepared', 'ownership'}.intersection(rel.parts)) or
                 (path.stat().st_size > 1024**2 and
                  path.suffix not in {'.png', '.pdf', '.svg', '.csv', '.md', '.py'}))
        if bulky:
            external[str(rel)] = record
            continue
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        if sha(dst) != record['sha256']:
            raise ValueError('Copy mismatch: ' + str(rel))
        included[str(rel)] = record
    manifest = dict(included=included, external=external, report=str(REPORT),
                    external_inputs_required=True, no_scientific_execution=True)
    (stage / 'publication_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    checked, missing = [], []
    for path in stage.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            target = target.strip().strip('<>').split('#', 1)[0]
            if not target or target.startswith(('http:', 'https:', 'mailto:', '/')):
                continue
            record = dict(file=str(path.relative_to(stage)), target=target)
            if (path.parent / target).resolve().is_file():
                checked.append(record)
                continue
            final = (PUBLISHER / REPORT / path.relative_to(stage).parent / target).resolve()
            try:
                relative = final.relative_to(PUBLISHER)
                result = subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + str(relative)],
                                        cwd=PUBLISHER, capture_output=True)
            except ValueError:
                result = None
            (checked if result is not None and result.returncode == 0 else missing).append(record)
    checks = dict(files=len(included) + 1, bytes=sum(v['bytes'] for v in included.values()),
                  external_files=len(external), checked_relative_links=checked,
                  missing_links=missing, ready=not missing,
                  manifest_sha256=sha(stage / 'publication_manifest.json'))
    (ROOT / 'publication_checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps({k: v for k, v in checks.items() if k != 'checked_relative_links'}))
    if missing:
        raise ValueError('Broken report links')


if __name__ == '__main__':
    main()
