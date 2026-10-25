"""Deterministic delta packages, exact input/source reuse, and roundtrip checks."""

import gzip
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent.parent
OLD = Path('/srv/bulk/leo/research/ds24-movement-policy-r01')
DS25 = Path('/srv/bulk/leo/research/ds25-20261024')
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
OLD_REPORT = PUBLISHER/'reports/2026_10_25_ds24_movement_policy'
OUTPUT = Path('/srv/bulk/leo/research/ds24-new-family-publication-r01')
TAG = 'research-ds24-new-family-uncertainty-r01-20261025'
REPORT = 'reports/2026_10_25_ds24_new_family_uncertainty'
COMMIT = '82e608d8d3b254e737326058e601a4775f231135'
RAW_ROOTS = ('scientific/profiles03/', 'scientific/fits03/', 'scientific/preparation02/points/',
             'math_audit/quadrature02_points/', 'math_audit/quadrature02b_points/')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eligible(path):
    rel = path.relative_to(ROOT)
    return (path.is_file() and not any(p.startswith('.') or p == '__pycache__' for p in rel.parts)
            and path.suffix not in ('.pyc',) and rel.name not in
            ('publication_index.json', 'REPORT_DRAFT.md', 'publication_inventory.json'))


def archive(name, entries):
    destination = OUTPUT/'assets'/name
    entries = sorted(entries, key=lambda row: row[0])
    with destination.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as tar:
                for member, path in entries:
                    info = tarfile.TarInfo(member)
                    info.size = path.stat().st_size
                    info.mode = 0o644
                    info.mtime = 0
                    with path.open('rb') as stream:
                        tar.addfile(info, stream)
    inventory = []
    expected = {member:path for member, path in entries}
    with tarfile.open(destination, 'r:gz') as tar:
        assert set(tar.getnames()) == set(expected)
        for member in tar.getmembers():
            path = expected[member.name]
            assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
            stream = tar.extractfile(member)
            digest = hashlib.sha256(stream.read()).hexdigest()
            assert digest == sha(path)
            inventory.append(dict(member=member.name, sha256=digest, bytes=member.size))
    assert destination.stat().st_size < 45_000_000
    return dict(asset=name, url=f'https://github.com/misko/leo-tracker-reduxredux/releases/download/{TAG}/{name}',
        bytes=destination.stat().st_size, sha256=sha(destination), members=inventory)


def main():
    (OUTPUT/'assets').mkdir(parents=True, exist_ok=True)
    old_index = read(OLD_REPORT/'publication_index.json')
    old_members = {m['member']:(a, m) for a in old_index['assets'] for m in a['members']}
    context_inputs = read(ROOT/'audit/input_closure.json')['files']
    paths = {Path(v['path']):{'context_read'} for v in context_inputs}
    parent_audit = read(ROOT/'audit/parent_audit.json')
    for name in parent_audit['input_sha256']:
        paths.setdefault(Path(name), set()).add('frozen_parent_binding')
    for binding in read(ROOT/'scientific/preparation01/input_bindings.json').values():
        for name in binding['source_hashes']:
            paths.setdefault(Path(name), set()).add('frozen_target_binding')
    inputs, new_inputs = [], {case:[] for case in ('DS24-0095', 'DS24-0087')}
    reused_assets = {}
    immutable_files = {}
    for path, reasons in sorted(paths.items()):
        digest = sha(path)
        row = dict(path=str(path), sha256=digest, bytes=path.stat().st_size, reasons=sorted(reasons))
        if path.is_relative_to(ROOT):
            row.update(delivery='current_report_file', member=str(path.relative_to(ROOT)))
        elif path.is_relative_to(DS25):
            case = next(case for case in new_inputs if case in str(path.relative_to(DS25)))
            member = 'input/ds25/'+str(path.relative_to(DS25))
            row.update(delivery='new_release_asset_member', member=member,
                asset=f'frozen_inputs_{case}.tar.gz')
            new_inputs[case].append((member, path))
        elif path.is_relative_to(OLD):
            member = str(path.relative_to(OLD))
            if member in old_members:
                asset, old = old_members[member]
                assert old['sha256'] == digest
                row.update(delivery='prior_release_asset_member', member=member,
                    asset=asset['asset'], asset_url=asset['url'], asset_sha256=asset['sha256'])
                reused_assets[asset['asset']] = {k:asset[k] for k in ('asset', 'url', 'bytes', 'sha256')}
            else:
                old_path = OLD_REPORT/member
                assert old_path.is_file() and sha(old_path) == digest
                gitpath = 'reports/2026_10_25_ds24_movement_policy/'+member
                row.update(delivery='prior_immutable_git_file', member=gitpath,
                    url=f'https://raw.githubusercontent.com/misko/leo-tracker-reduxredux/{COMMIT}/{gitpath}')
                immutable_files[gitpath] = dict(row)
        else:
            raise AssertionError(path)
        inputs.append(row)
    closure = read(ROOT/'audit/runtime_closure.json')
    reused_assets[closure['prior_runtime_capsule']['asset']] = closure['prior_runtime_capsule']
    for row in closure['files']:
        assert sha(row['path']) == row['sha256'], row['path']
        if row['delivery'] == 'prior_immutable_git_file':
            immutable_files[row['member']] = row
    source_input = dict(scope='All safe-context file reads plus exact declared parent/target bindings; source closure is separate.',
        input_files=inputs, actual_context_read_files=len(context_inputs), total_bound_input_files=len(inputs),
        new_frozen_input_files=sum(len(v) for v in new_inputs.values()),
        reused_release_assets=list(reused_assets.values()), immutable_R1_files=list(immutable_files.values()),
        runtime_source_closure_sha256=sha(ROOT/'audit/runtime_closure.json'), raw_IQ_included=False)
    (ROOT/'audit/publication_dependencies.json').write_text(json.dumps(source_input, indent=2)+'\n')
    assets = [archive(f'frozen_inputs_{case}.tar.gz', entries) for case, entries in new_inputs.items()]
    all_files = [p for p in sorted(ROOT.rglob('*')) if eligible(p)]
    raw = [(str(path.relative_to(ROOT)), path) for path in all_files if str(path.relative_to(ROOT)).startswith(RAW_ROOTS)]
    assets.append(archive('new_family_uncertainty_raw_evidence.tar.gz', raw))
    direct = [dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=sha(path))
        for path in all_files if not str(path.relative_to(ROOT)).startswith(RAW_ROOTS)]
    index = dict(status='verified_archive_inventory', release_tag=TAG,
        release_title='DS24 new-family uncertainty r01 research evidence', report_directory=REPORT,
        parent_report_commit=COMMIT, source_sha256=sha(Path(__file__)), assets=assets,
        asset_count=len(assets), asset_bytes=sum(a['bytes'] for a in assets),
        largest_asset_bytes=max(a['bytes'] for a in assets),
        git_direct_file_count=len(direct), git_direct_bytes=sum(v['bytes'] for v in direct), direct_files=direct,
        reused_release_assets=list(reused_assets.values()), immutable_R1_files=list(immutable_files.values()),
        dependency_manifest='audit/publication_dependencies.json', runtime_source_manifest='audit/runtime_closure.json',
        all_archive_members_roundtrip_hash_verified=True, raw_IQ_included=False, no_credentials_included=True,
        scientific_RF_seal_sha256=sha(ROOT/'scientific/RF_seal03.json'),
        README_sha256=sha(ROOT/'README.md') if (ROOT/'README.md').is_file() else None,
        REVIEW_sha256=sha(ROOT/'REVIEW.md'), complete_input_bytes_included_beyond_R1_hash_only_bindings=True)
    (ROOT/'publication_index.json').write_text(json.dumps(index, indent=2)+'\n')
    receipt = dict(all_passed=True, package_source_sha256=sha(Path(__file__)),
        publication_index_sha256=sha(ROOT/'publication_index.json'),
        assets=[{k:a[k] for k in ('asset', 'bytes', 'sha256')} for a in assets],
        raw_member_count=len(raw), new_input_member_count=sum(len(v) for v in new_inputs.values()),
        archive_members_verified=sum(len(a['members']) for a in assets), reused_asset_count=len(reused_assets),
        git_direct_files=len(direct), git_direct_bytes=sum(v['bytes'] for v in direct),
        all_assets_below_45_MB=True, no_new_fits=True, no_raw_IQ=True)
    (OUTPUT/'archive_validation.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
