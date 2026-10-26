"""Package audited saved artifacts; performs no scientific inference."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
REPORT = Path('reports/2026_10_26_ds24_detector_response')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    seal_path = ROOT / 'audit/final_seal.json'
    seal = json.loads(seal_path.read_text())
    assert seal['all_passed'] and seal['passed_receipts'] >= 6
    for name, digest in seal['files'].items():
        assert sha(Path(name)) == digest, name
    selected = {}
    for branch in ('measurement', 'influence', 'recorded'):
        manifest = json.loads((ROOT / branch / 'lean_publication.json').read_text())
        selected[branch] = {r['path']: r['sha256'] for r in manifest['published']}
        for name, digest in selected[branch].items():
            assert sha(Path(name)) == digest, name
    stage = ROOT / 'publication'
    stage.mkdir(exist_ok=False)
    included, external = {}, {}
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if (not path.is_file()
                or {'publication', '__pycache__', '.pytest_cache'}.intersection(rel.parts)
                or path.name in {'publication_receipt.json', 'publication_checks.json'}):
            continue
        record = {'source': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        if (rel.parts[0] in selected and str(path) not in selected[rel.parts[0]]
                and path.name != 'lean_publication.json'):
            external[str(rel)] = record
            continue
        assert path.stat().st_size < 90_000_000, str(path)
        dest = stage / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        assert sha(dest) == record['sha256']
        included[str(rel)] = record
    manifest = {'included': included, 'external': external, 'report': str(REPORT),
                'external_inputs_required': True, 'scientific_execution': False,
                'audit_seal_sha256': sha(seal_path)}
    (stage / 'publication_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    checked, missing = [], []
    for path in stage.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            target = target.strip().strip('<>').split('#', 1)[0]
            if not target or target.startswith(('http:', 'https:', 'mailto:', '/')):
                continue
            record = {'file': str(path.relative_to(stage)), 'target': target}
            if (path.parent / target).resolve().exists():
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
    checks = {'files': len(included) + 1, 'bytes': sum(v['bytes'] for v in included.values()),
              'external_files': len(external), 'checked_relative_links': checked,
              'missing_links': missing, 'ready': not missing,
              'manifest_sha256': sha(stage / 'publication_manifest.json')}
    (ROOT / 'publication_checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps({k: v for k, v in checks.items() if k != 'checked_relative_links'}))
    assert not missing, missing


if __name__ == '__main__':
    main()
