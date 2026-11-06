"""Bind the fixed-prior experiment and reuse the existing isolated kernel comparator."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--candidate-first', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    root.mkdir(exist_ok=False)
    report = Path(__file__).resolve().parent
    module = Path('leo/analysis/localization_v3/hierarchical.py')
    driver = Path('reports/2026_11_06_algo07v3_covariance_native/run_pair.py')
    paths = [Path(__file__), driver, driver.with_name('run_baseline.sh'),
             Path('tools/qualify_algo07v3_cli.sh'), Path('tools/compare_algo07v3_runs.py'),
             args.request, *Path('src').rglob('*.py')]
    for side in ('baseline', 'candidate'):
        source, target = report/f'{side}-src'/module, root/f'{side}-src'/module
        target.parent.mkdir(parents=True)
        target.write_bytes(source.read_bytes())
        (root/f'{side}-sources.json').write_text(json.dumps(
            {str(module):digest(target)},indent=2)+'\n')
        paths.extend((source,target,root/f'{side}-sources.json'))
    bindings = {str(path.resolve()):digest(path) for path in paths}
    (root/'complete-source-bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
    command = [sys.executable,'-B',str(driver),'--root',str(root),'--request',str(args.request)]
    if args.candidate_first:
        command.append('--candidate-first')
    subprocess.run(command,check=True)
    assert all(digest(Path(path))==sha for path,sha in bindings.items())
    comparison = json.loads((root/'comparison.json').read_bytes())
    assert comparison['exact_owned_science_and_artifacts']
    (root/'complete-source-check.json').write_text(json.dumps(dict(
        unchanged=True,exact=True,production_modified=False),indent=2)+'\n')
    print(json.dumps(comparison['observed_process_seconds']),flush=True)


if __name__=='__main__':
    main()
