"""Final local publication/schema/link/custody checks; no scientific evaluation."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OLD = Path('/srv/bulk/leo/research/ds24-movement-policy-r01')
OUT = Path('/srv/bulk/leo/research/ds24-new-family-publication-r01')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def custody():
    original = read(OLD/'preflight.json')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=no'], cwd=REPO, text=True)
    diff = hashlib.sha256(subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=REPO)).hexdigest()
    assert head == original['working_git_head']
    assert status == original['tracked_status']
    assert diff == original['tracked_diff_sha256']
    return dict(all_passed=True, head=head, tracked_diff_sha256=diff,
        tracked_dirty_files=len(status.splitlines()), tracked_work_preserved=True,
        original_preflight_sha256=sha(OLD/'preflight.json'))


def main():
    index = read(ROOT/'publication_index.json')
    assert index['README_sha256'] == sha(ROOT/'README.md')
    assert index['REVIEW_sha256'] == sha(ROOT/'REVIEW.md')
    assert len(index['assets']) == 3 and index['asset_bytes'] == 70843110
    assert sum(len(v['members']) for v in index['assets']) == 543
    direct = {v['path'] for v in index['direct_files']} | {'publication_index.json'}
    for row in index['direct_files']:
        assert (ROOT/row['path']).stat().st_size == row['bytes']
        assert sha(ROOT/row['path']) == row['sha256']
    links = []
    for name in sorted(direct):
        path = ROOT/name
        if path.suffix != '.md':
            continue
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            target = unquote(target.strip('<>').split('#', 1)[0])
            if not target or re.match(r'^[a-zA-Z]+://', target):
                continue
            assert not target.startswith('/'), (name, target)
            relative = str((path.parent/target).resolve().relative_to(ROOT))
            assert relative in direct, (name, target, relative)
            links.append((name, target))
    json_files = [name for name in direct if name.endswith('.json')]
    for name in json_files:
        read(ROOT/name)
    for path, digest in read(ROOT/'scientific/RF_seal03.json')['files'].items():
        assert sha(path) == digest
    assert read(ROOT/'evaluation/reporting_audit.json')['all_passed']
    state = custody()
    result = dict(all_passed=True, source_sha256=sha(__file__), index_sha256=sha(ROOT/'publication_index.json'),
        checked_relative_links=len(links), checked_direct_JSON_files=len(json_files),
        direct_report_files=len(direct), direct_report_bytes=sum((ROOT/name).stat().st_size for name in direct),
        all_scientific_seal_bindings_unchanged=True, root_workspace_custody=state,
        README_sha256=sha(ROOT/'README.md'), REVIEW_sha256=sha(ROOT/'REVIEW.md'), no_new_fits=True)
    (OUT/'local_publication_check.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
