"""Copy the report's compact reproducibility bundle; never copy raw IQ."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    target = args.destination
    if target.exists():
        raise FileExistsError('Use a fresh report directory; do not overwrite a published bundle')
    target.mkdir(parents=True)
    selected = [ROOT / name for name in ['REPORT.md', 'PLAN.md', 'split.json',
        'INTEGRATION_REVIEW.md', 'POSITION_APPROVAL.json',
        'COHERENT_EXPANSION_PLAN.md', 'halfcell_diagnostic.py', 'publish_bundle.py',
        'acquisition_missing_diagnosis.py', 'acquisition_missing_diagnosis.json',
        'acquisition_missing_diagnosis.png', 'acquisition_missing_diagnosis.pdf']]
    compressed = []
    for directory in ['prediction', 'timing', 'validation']:
        for path in (ROOT / directory).iterdir():
            if path.is_file() and path.suffix in {'.md', '.py', '.png', '.pdf', '.csv'}:
                selected.append(path)
            elif path.is_file() and path.suffix == '.json':
                if path.stat().st_size <= 250_000:
                    selected.append(path)
                else:
                    compressed.append(path)
    for name in ['protocol.json', 'summary.json']:
        selected.append(ROOT / 'halfcell_diagnostic' / name)
    selected.extend((ROOT / 'validation' / 'position_harness').glob('*.py'))
    # Preserve bulky metadata as small lossless gzip files, without raw samples.
    records = []
    for source in sorted(set(selected)):
        relative = source.relative_to(ROOT)
        destination = target / ('README.md' if relative == Path('REPORT.md') else relative)
        destination.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy2(source, destination)
        records.append(dict(source=str(source), published_path=str(destination.relative_to(target)),
            source_sha256=digest(source), published_sha256=digest(destination),
            bytes=destination.stat().st_size, encoding='identity'))
    for source in compressed:
        if source in selected:
            continue
        destination = target / (str(source.relative_to(ROOT)) + '.gz')
        destination.parent.mkdir(exist_ok=True, parents=True)
        with destination.open('xb') as output:
            with gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as stream:
                stream.write(source.read_bytes())
        records.append(dict(source=str(source), published_path=str(destination.relative_to(target)),
            source_sha256=digest(source), published_sha256=digest(destination),
            bytes=destination.stat().st_size, encoding='gzip'))
    manifest = dict(schema='missed-visit-publication-bundle/v1', files=records,
        raw_IQ_published=False, full_study_directory=str(ROOT),
        note='Absolute paths in source receipts identify immutable local authorities. '
             'Bulky prediction metadata is compressed. Full per-target RF outcomes '
             'remain in the study directory and are bound by summary source hashes.')
    (target / 'publication_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(files=len(records), bytes=sum(r['bytes'] for r in records),
        destination=str(target)), indent=2))


if __name__ == '__main__':
    main()
