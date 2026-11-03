"""Verify persisted source bindings and preserve fragment-support diagnostics."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    cache = {}
    def digest(path):
        path = str(path)
        if path not in cache:
            cache[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return cache[path]
    documents = 0
    for path in sorted(HERE.glob('*.json')):
        doc = json.loads(path.read_text())
        for source, expected in doc.get('sources', {}).items():
            assert digest(source) == expected, (str(path), source)
        documents += 1
    donors = {}
    for index in (0, 1):
        doc = json.loads((HERE / f'donor-{index}.json').read_text())
        donors[str(index)] = dict(Counter(len(lane['tracks']) for lane in doc['lanes']))
    repeated = []
    identities = json.loads((HERE / 'identity-audit.json').read_text())
    for row in identities['rows']:
        doc = json.loads((HERE / f"input-{row['index']:02d}.json").read_text())
        meta = {t['track_id']: t for t in doc['tracks']}
        counts = Counter((v['map_norad'], meta[t]['rf_hz'], meta[t]['receiver']) for t, v in row['arms']['signed'].items())
        repeated.append(dict(index=row['index'], repeated_same_source_rf_receiver_groups=sum(v > 1 for v in counts.values()), maximum_tracks_per_group=max(counts.values())))
    paths = [Path(__file__), HERE / 'identity-audit.json', HERE / 'donor-0.json', HERE / 'donor-1.json', HERE / 'sequence-summary.json', HERE / 'compatible-summary.json', HERE / 'additional-summary.json']
    result = dict(json_documents_checked=documents, unique_source_files_verified=len(cache), donor_tracks_per_source_histogram=donors, repeated_groups=repeated, source_bindings_passed=True, sources={str(p): digest(p) for p in paths})
    with (HERE / 'final-audit.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}, indent=2))


if __name__ == '__main__':
    main()
