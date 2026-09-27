"""Verify publication integrity without executing archived detector code."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inventory=json.loads((HERE/'archive_inventory.json').read_text())
    included=[f for f in inventory['files'] if f['included']]
    for f in included:
        path=ROOT/f['path']
        assert path.stat().st_size==f['bytes'] and digest(path)==f['sha256'], str(path)
        if path.suffix=='.json':json.loads(path.read_text())
        if path.suffix=='.jsonl':
            for line in path.read_text().splitlines():
                if line.strip():json.loads(line)
    for f in inventory['files']:
        if not f['included']:assert not (ROOT/f['path']).exists(), f['path']
    snapshots=json.loads((HERE/'source_snapshots.json').read_text())['files']
    for f in snapshots:
        assert digest(HERE/f['archive_path'])==f['sha256']
        assert f['matches_recorded_hash'] and f['sha256'] in f['recorded_hashes']
    chart=json.loads((HERE/'chart_data.json').read_text())
    research=HERE.parent/'2026_09_27_ds5_cached_tracking'
    for name,expected in chart['sources_sha256'].items():
        assert digest(research/name)==expected
    for row in chart['cpu_and_quality']:
        assert abs(row['reference_cpu_ms']/row['candidate_cpu_ms']-row['speedup'])<1e-8
    holdout=[r for r in chart['cpu_and_quality'] if r['cohort']=='Recorded holdout']
    assert [(r['retained'],r['reference_positive']) for r in holdout]==[(37,43),(5,6)]
    assert all(r['retained']/r['reference_positive']<.97 for r in holdout)
    links=0
    for name in ('README.md','CATALOG.md'):
        for link in re.findall(r'\]\(([^)]+)\)',(HERE/name).read_text()):
            if link.startswith(('http:','https:','#')):continue
            path=HERE/link.split('#')[0]
            assert path.exists(), f'{name}: {link}'
            links+=1
    for name in ('cpu-comparison','quality-transfer','proposal-coverage'):
        assert (HERE/'figures'/f'{name}.png').read_bytes().startswith(b'\x89PNG')
        assert '<svg' in (HERE/'figures'/f'{name}.svg').read_text()
    print(json.dumps({'archived_files_verified':len(included),'source_snapshots_verified':len(snapshots),
        'report_and_catalog_links_verified':links,'figures_verified':3,'holdout_failure_preserved':True}))


if __name__=='__main__':main()
