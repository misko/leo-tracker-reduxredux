"""Final saved-artifact and publication-link closure, without scientific work."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    terminal = [read(HERE / name) for name in ('portions_terminal.json', 'matched_law_terminal.json')]
    assert all(row['all_passed'] for row in terminal)
    references = []
    for relative in ('portions/RF_seal.json', 'portions/report/report_seal.json',
                     'matched_law/RF_seal.json', 'matched_law/report/seal.json'):
        path = ROOT / relative
        assert all(sha(target) == h for target, h in read(path)['files'].items())
        references.append(path)
    references += [ROOT / relative for relative in ('portions/FINDINGS.md', 'matched_law/FINDINGS.md')]
    critique = (HERE / 'REVIEW_CRITIQUE_B.md').read_text()
    prior_links = re.findall(r'https://github\.com/misko/leo-tracker-reduxredux/blob/([a-f0-9]{40})/([^\s)]+)', critique)
    publisher = '/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022'
    for revision, path in prior_links:
        subprocess.run(['git', 'cat-file', '-e', revision + ':' + path], cwd=publisher, check=True)
    assert len(prior_links) == 5 and '../../ds24-' not in critique
    diff = subprocess.check_output(['git', 'diff', '--binary', '--no-ext-diff'], cwd='/home/mouse9911/gits/leo-tracker-reduxredux')
    assert hashlib.sha256(diff).hexdigest() == 'add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b'
    files = {str(path): sha(path) for path in sorted(HERE.iterdir()) if path.is_file() and path.name != 'final_seal.json'}
    result = dict(all_passed=True, files=files, scientific_and_reporting_references={str(path): sha(path) for path in references},
        independent_terminal_checks=sum(len(row['checks']) for row in terminal),
        cumulative_audit_numerical_seconds=terminal[-1]['cumulative_audit_seconds'], audit_numeric_cap_seconds=180,
        prior_publication_links=[dict(commit=revision, path=path, git_object_verified=True) for revision, path in prior_links],
        source_and_figures_review='Both branch findings and all five figures inspected against terminal results; affine/native gauge, finite-pool versus absolute precision and off-law c sensitivity are explicit.',
        root_document_review='Latest README/REVIEW read; only objective-units clarification requested. Root documents are deliberately not hash-bound here, avoiding a reporting-update dependency.',
        scope='No new physical propagation, catalogue search, synthetic scientific vector, position fit, geographic truth or operational adoption. Exact original dirty tracked diff preserved.')
    with (HERE / 'final_seal.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=True, files=len(files), terminal_checks=result['independent_terminal_checks'],
        final_seal_sha256=sha(HERE / 'final_seal.json'))))


if __name__ == '__main__':
    main()
