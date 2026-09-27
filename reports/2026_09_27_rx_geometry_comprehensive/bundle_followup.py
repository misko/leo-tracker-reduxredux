"""Archive selected follow-up receipts; requires the original reports directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
SELECTED = {
    '2026_09_27_rx_transfer_concentration': (
        'results.json', 'grouped-rebuild-summary.json',
    ),
    '2026_09_27_rx_disjoint_confirmation': (
        'manifest.json', 'contract.json', 'inventory.json', 'summary.json',
        'summary-v2.json', 'regression-diagnostic.json',
        'failure-components-scan-fw-127d8fc36e804ae2.json',
        'failure-components-scan-fw-8f4f960d9db67798.json',
        'source-audit-scan-fw-127d8fc36e804ae2.json',
        'source-audit-scan-fw-8f4f960d9db67798.json',
        'source-audit-summary.json',
    ),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', type=Path)
    args = parser.parse_args()
    entries = []
    for directory, names in SELECTED.items():
        source = args.reports / directory
        paths = set(source.glob('*.md')) | set(source.glob('*.py'))
        paths.update(source / name for name in names)
        for path in sorted(paths):
            relative = path.relative_to(args.reports)
            destination = HERE / 'followup_sources' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            entries.append({'path': str(relative), 'bytes': path.stat().st_size,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (HERE / 'followup_sources/manifest.json').write_text(json.dumps(entries, indent=2) + '\n')
    print(f'Archived {len(entries)} receipts ({sum(e["bytes"] for e in entries):,} bytes)')


if __name__ == '__main__':
    main()
