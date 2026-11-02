"""Select compact evidence and validate the report before explicit Git publication."""
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    selected = set()
    for branch in ('orbits', 'diagnostics', 'eval'):
        p = ROOT / branch / 'publication_manifest.json'
        manifest = json.loads(p.read_text())
        for row in manifest['allowlist']:
            rel = row['path']
            path = ROOT / rel
            assert path.is_file(), path
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], path
            selected.add(rel)
        selected.add(str(p.relative_to(ROOT)))
    selected.update(['README.md', 'inventory.py', 'aggregate.py', 'prepare_publication.py',
                     'initial_ranking.csv', 'run_manifest.json', 'verified_ranking.json',
                     'top10_results.csv', 'top10_overview.png', 'all_interventions.png'])
    table = []
    for line in (ROOT / 'README.md').read_text().splitlines():
        if line.startswith('| DS26-'):
            table.append([x.strip() for x in line.strip('|').split('|')])
    assert len(table) == 10
    with (ROOT / 'findings.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['case', 'fitted_c_error_km', 'published_glrt_percent', 'finding', 'next_discriminator'])
        writer.writerows(table)
    selected.add('findings.csv')
    links = []
    for rel in selected:
        p = ROOT / rel
        if p.suffix != '.md':
            continue
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', p.read_text()):
            if target.startswith(('http:', 'https:', '#')):
                continue
            target = target.split('#')[0]
            q = (p.parent / target).resolve()
            assert q.is_file(), (p, target)
            assert str(q.relative_to(ROOT)) in selected, ('linked file omitted', p, q)
            links.append([rel, target])
    files = []
    for rel in sorted(selected):
        p = ROOT / rel
        files.append(dict(path=rel, bytes=p.stat().st_size,
                          sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    result = dict(allowlist=files, total_bytes=sum(r['bytes'] for r in files),
                  markdown_links_verified=len(links),
                  scope='Report and compact evidence only; no production changes or raw TLE duplication')
    (ROOT / 'publication_manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'allowlist'}))


if __name__ == '__main__':
    main()
