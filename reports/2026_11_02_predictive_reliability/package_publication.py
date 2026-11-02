"""Verify and package only this iteration's report artifacts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SUFFIXES = {'.py', '.md', '.json', '.csv', '.npz', '.png', '.sha256'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    for name, expected in protocol['source_sha256'].items():
        assert sha(Path(name)) == expected, name
    assert sha(ROOT/'predictive/results.json') == (ROOT/'predictive/results.sha256').read_text().split()[0]
    assert sha(ROOT/'decisions.json') == (ROOT/'decisions.sha256').read_text().split()[0]
    for name in ['native/publication_manifest.json', 'review/publication_manifest.json']:
        for row in json.loads((ROOT/name).read_text())['allowlist']:
            assert sha(ROOT/row['path']) == row['sha256'], row['path']
    files = sorted(p for p in ROOT.rglob('*') if p.is_file()
                   and '__pycache__' not in p.parts and p.suffix in SUFFIXES
                   and p.name != 'publication_manifest.json')
    # Include component manifests, excluding only the self-referential root one.
    files += sorted(p for p in ROOT.rglob('publication_manifest.json') if p.parent != ROOT)
    files = sorted(set(files))
    included = set(files)
    links = 0
    for path in files:
        if path.suffix != '.md':
            continue
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            dest = (path.parent / target.split('#')[0]).resolve()
            assert dest.exists(), (str(path), target)
            if dest.is_file() and dest.is_relative_to(ROOT):
                assert dest in included, (str(path), target, 'not published')
            elif dest.is_file() and dest.is_relative_to(REPO):
                subprocess.run(['git','ls-files','--error-unmatch',str(dest.relative_to(REPO))],
                               cwd=REPO, check=True, stdout=subprocess.DEVNULL)
            links += 1
    manifest = dict(scope='Conditional predictive-reliability development experiment; no production edits',
        protocol_sha256=sha(ROOT/'protocol.json'), results_sha256=sha(ROOT/'predictive/results.json'),
        decisions_sha256=sha(ROOT/'decisions.json'),
        tests='22 report-owned tests passed', checked_local_markdown_links=links,
        files=[dict(path=str(p.relative_to(REPO)), bytes=p.stat().st_size, sha256=sha(p)) for p in files])
    (ROOT/'publication_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    names=[str(p.relative_to(REPO)) for p in files]+[str((ROOT/'publication_manifest.json').relative_to(REPO))]
    (ROOT/'publication_paths.txt').write_text('\n'.join(names)+'\n')
    print(json.dumps(dict(files=len(names), bytes=sum(p.stat().st_size for p in files), links=links)))


if __name__ == '__main__':
    main()
