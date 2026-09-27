"""Snapshot explicitly referenced evidence from the original research workspace."""
from pathlib import Path
import hashlib
import json
import re
import shutil

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def main():
    refs = set()
    for name in ('README.md', 'EXPERIMENT_LOG.md'):
        refs.update(re.findall(r'\]\(sources/([^\)]+)\)', (HERE / name).read_text()))
    refs.discard('INDEX.md')
    # Source receipts for every plotting input, including fold-specific fits.
    from build_figures import SOURCES, B
    refs.update(str(p.relative_to(REPORTS)) for p in SOURCES.values())
    for pattern in ('track-random-intercept-refined-fold-*.json',
                    'ratio-random-intercept-fold-*.json'):
        refs.update(str(p.relative_to(REPORTS)) for p in B.glob(pattern))
    refs.update({
        '2026_09_27_roof_direction_subset/REPORT.md',
        '2026_09_27_roof_location_geometry/ROBUST_PROTOCOL.md',
        '2026_09_27_roof_balanced_confirmation/RECEPTION_IDENTITY_OVERRIDE_RESULTS.md',
    })
    manifest = []
    for rel in sorted(refs):
        src = REPORTS / rel
        dst = HERE / 'sources' / rel
        if not src.is_file():
            raise FileNotFoundError(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        manifest.append({'path': rel, 'bytes': src.stat().st_size,
                         'sha256': hashlib.sha256(src.read_bytes()).hexdigest()})
    (HERE / 'sources' / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    lines = ['# Archival evidence snapshots', '',
             'These are byte-for-byte research receipts. Historical links and absolute paths',
             'inside them may refer to the original workspace and are not portable.',
             'The main report, experiment log, and figures are the portable reading path.',
             'Raw RF and large per-location/per-track working shards are omitted.',
             'The transfer summary retains per-track results and source-shard hashes;',
             'the six original source shards are not duplicated here.', '',
             'Checksums and original reports-relative paths: [manifest.json](manifest.json).', '']
    lines.extend(f'- [{r["path"]}]({r["path"]})' for r in manifest)
    (HERE / 'sources' / 'INDEX.md').write_text('\n'.join(lines) + '\n')
    print(f'Snapshotted {len(manifest)} files, {sum(r["bytes"] for r in manifest):,} bytes')


if __name__ == '__main__':
    main()
