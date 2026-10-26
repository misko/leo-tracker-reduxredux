"""Verify publication bytes, compressed-source hashes and README links."""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('publication', type=Path)
    args = parser.parse_args()
    root = args.publication.resolve()
    manifest = json.loads((root / 'publication_manifest.json').read_text())
    seen = set()
    errors = []
    for entry in manifest['files']:
        name = entry['published_path']
        if name in seen:
            errors.append('duplicate ' + name)
        seen.add(name)
        data = (root / name).read_bytes()
        if sha(data) != entry['published_sha256']:
            errors.append('published hash ' + name)
        decoded = gzip.decompress(data) if entry['encoding'] == 'gzip' else data
        if sha(decoded) != entry['source_sha256']:
            errors.append('decoded hash ' + name)
        if sha(Path(entry['source']).read_bytes()) != entry['source_sha256']:
            errors.append('source changed after packaging ' + name)
        if name.endswith(('.json', '.json.gz')):
            json.loads(decoded)
    links = re.findall(r'\]\(([^)]+)\)', (root / 'README.md').read_text())
    for link in links:
        if link.startswith(('https://', 'http://', '#')):
            continue
        path = root / link.split('#')[0]
        if not path.is_file():
            errors.append('missing README link ' + link)
    print(json.dumps({'files': len(seen), 'README_links': len(links),
                      'bytes': sum(x['bytes'] for x in manifest['files']),
                      'errors': errors}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
