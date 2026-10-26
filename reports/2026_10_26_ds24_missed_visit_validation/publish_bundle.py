"""Publish compact final evidence, retaining declared external raw dependencies."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
R01 = ROOT.with_name('ds24-missed-visit-r01')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    target = args.destination
    if target.exists():
        raise FileExistsError('Use a new publication directory')
    mapping = {
        ROOT / 'prediction': Path('prediction'),
        ROOT / 'timing': Path('timing'),
        ROOT / 'validation': Path('validation'),
        R01 / 'expansion' / 'prediction': Path('coherent/prediction'),
        ROOT / 'timing' / 'expansion_v2': Path('coherent/timing'),
        R01 / 'validation' / 'coherent_application': Path('coherent/validation'),
        R01 / 'held_validation' / 'prediction': Path('held/prediction'),
        ROOT / 'timing' / 'held': Path('held/timing'),
        R01 / 'held_validation' / 'validation': Path('held/validation'),
        ROOT / 'validation' / 'held_graph': Path('held/graph'),
    }
    entries = [(ROOT / 'REPORT.md', Path('README.md')),
               (ROOT / 'PLAN.md', Path('PLAN.md')),
               (Path(__file__), Path('publish_bundle.py')),
               (ROOT / 'verify_publication.py', Path('verify_publication.py')),
               (R01 / 'HELD_VALIDATION_PLAN.md', Path('HELD_VALIDATION_PLAN.md')),
               (R01 / 'HELD_VALIDATION_APPROVAL.json', Path('HELD_VALIDATION_APPROVAL.json')),
               (R01 / 'EXPANSION_APPROVAL_V2.json', Path('EXPANSION_APPROVAL_V2.json'))]
    allowed = {'.md', '.py', '.png', '.pdf', '.csv', '.json'}
    for source_dir, relative in mapping.items():
        if not source_dir.is_dir():
            raise FileNotFoundError(source_dir)
        for source in source_dir.iterdir():
            if source.is_file() and source.suffix in allowed:
                entries.append((source, relative / source.name))
        for subdir in ('figures', 'sources', 'case_audits', 'source_seals'):
            for source in (source_dir / subdir).glob('*'):
                if source.is_file() and source.suffix in allowed:
                    entries.append((source, relative / subdir / source.name))
        if relative == Path('held/graph'):
            for pattern in ('jobs/*/*.json', 'graphs/*/*/audit.json'):
                for source in source_dir.glob(pattern):
                    entries.append((source, relative / source.relative_to(source_dir)))
    target.mkdir(parents=True)
    records = []
    for source, relative in entries:
        compressed = source.suffix == '.json' and source.stat().st_size > 250_000
        destination = target / (str(relative) + '.gz' if compressed else relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if compressed:
            with destination.open('xb') as output:
                with gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as stream:
                    stream.write(source.read_bytes())
        else:
            shutil.copy2(source, destination)
        records.append(dict(source=str(source), source_sha256=sha(source),
                            published_path=str(destination.relative_to(target)),
                            published_sha256=sha(destination),
                            encoding='gzip' if compressed else 'identity',
                            bytes=destination.stat().st_size))
    manifest = dict(schema='missed-visit-final-publication/v1', files=records,
                    raw_IQ_published=False,
                    full_studies=[str(R01), str(ROOT)],
                    scope='Compact outcomes, figures, sources and audit hashes. '
                          'Native IQ, full scoring checkpoints and regional run '
                          'trees remain external and are bound by their seals. '
                          'Published source retains its exact study paths.')
    (target / 'publication_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(files=len(records), bytes=sum(r['bytes'] for r in records),
                          destination=str(target)), indent=2))


if __name__ == '__main__':
    main()
