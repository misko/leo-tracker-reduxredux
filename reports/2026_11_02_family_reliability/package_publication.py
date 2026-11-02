"""Build an explicit report-only publication list; never stage or push files."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    paths = {p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py', '.md', '.csv', '.png', '.json'}}
    paths.discard(ROOT / 'publication_manifest.json')
    paths.add(ROOT / 'verification_tests.txt')
    for section in ['solver', 'family', 'predictive', 'population']:
        manifest = ROOT / section / 'publication_manifest.json'
        data = json.loads(manifest.read_text())
        assert 'allowlist' in data, f'{manifest}: missing explicit allowlist'
        for entry in data['allowlist']:
            if isinstance(entry, str):
                name, expected = entry, data['files'][entry]
            else:
                name, expected = entry['path'], entry
            path = ROOT / name
            assert path.is_relative_to(ROOT) and path.is_file(), path
            assert digest(path) == expected['sha256'], f'Stale manifest: {path}'
            assert path.stat().st_size == expected['bytes'], path
            paths.add(path)
        paths.add(manifest)
    for case in ['DS26-0070', 'DS26-0309']:
        folder = ROOT / 'combined' / case
        for path in folder.glob('*.json'):
            if path.name not in {'results.json', 'ensemble.json'} and not path.name.endswith('.rf.json'):
                paths.add(path)
        paths.add(folder / 'qualified_ensemble_rf.json')
    # Links into earlier reports must already be tracked; current report links
    # must be present in the explicit publication set.
    issues = []
    for path in paths:
        if path.suffix != '.md':
            continue
        for raw in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            target = raw.split('#')[0].strip('<>')
            if not target or '://' in target:
                continue
            dest = (path.parent / target).resolve()
            if dest == ROOT / 'publication_manifest.json':
                continue
            if dest.is_relative_to(ROOT):
                if dest not in paths:
                    issues.append((str(path.relative_to(ROOT)), target))
            elif dest.is_relative_to(REPO):
                result = subprocess.run(['git', 'ls-files', '--error-unmatch', str(dest.relative_to(REPO))],
                                        cwd=REPO, capture_output=True)
                if result.returncode:
                    issues.append((str(path.relative_to(ROOT)), target))
            else:
                issues.append((str(path.relative_to(ROOT)), target))
    assert not issues, f'Unpublished local links: {issues}'
    entries = [dict(path=str(p.relative_to(ROOT)), sha256=digest(p), bytes=p.stat().st_size)
               for p in sorted(paths)]
    payload = dict(scope='Report-local offline experiments; no production changes',
                   allowlist=entries, count=len(entries), total_bytes=sum(e['bytes'] for e in entries))
    (ROOT / 'publication_manifest.json').write_text(json.dumps(payload, indent=2) + '\n')
    (ROOT / 'publication_paths.txt').write_text('\n'.join(str(p.relative_to(REPO)) for p in sorted(paths)) +
        '\n' + str((ROOT / 'publication_manifest.json').relative_to(REPO)) + '\n')
    print(json.dumps({k:v for k,v in payload.items() if k != 'allowlist'}))


if __name__ == '__main__':
    main()
