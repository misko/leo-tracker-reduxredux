"""Import/context-only source closure with immutable reuse of R1 assets."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import execution03
import adapter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREVIOUS = Path('/srv/bulk/leo/research/ds24-movement-policy-r01')
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
OLD_REPORT = PUBLISHER/'reports/2026_10_25_ds24_movement_policy'
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
CONTROLS = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
WITNESS = Path('/srv/bulk/leo/research/ds24-receiver-shift-witness-20261025')
COMMIT = '82e608d8d3b254e737326058e601a4775f231135'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    # The safe loader reconstructs saved inputs only. No fitter or target
    # likelihood is called; conditional imports are captured as well.
    contexts = [adapter.load_context(case) for case in adapter.CASES]
    assert len(contexts) == 2
    old_inventory_path = PREVIOUS/'audit/runtime_source_inventory.json'
    old_inventory = read(old_inventory_path)
    previous = {row['path']:row for row in old_inventory['files']}
    index_path = OLD_REPORT/'publication_index.json'
    index = read(index_path)
    capsule = next(row for row in index['assets'] if row['asset'] == 'actual_runtime_source_capsule.tar.gz')
    members = {row['member']:row for row in capsule['members']}
    paths = set()
    roots = (REPO/'src', REPO/'tools', ROOT, PREVIOUS, CONTROLS, WITNESS)
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and any(path.is_relative_to(root) for root in roots):
                paths.add(path)
    files, new_external = [], []
    for path in sorted(paths):
        digest = sha(path)
        row = dict(path=str(path), sha256=digest, bytes=path.stat().st_size)
        if path.is_relative_to(ROOT):
            row.update(delivery='current_report_file', member=str(path.relative_to(ROOT)))
        elif str(path) in previous and previous[str(path)]['sha256'] == digest:
            old = previous[str(path)]
            assert members[old['member']]['sha256'] == digest
            row.update(delivery='prior_release_asset_member', member=old['member'],
                asset=capsule['asset'], asset_url=capsule['url'], asset_sha256=capsule['sha256'])
        elif path.is_relative_to(PREVIOUS) and (OLD_REPORT/path.relative_to(PREVIOUS)).is_file():
            member = 'reports/2026_10_25_ds24_movement_policy/'+str(path.relative_to(PREVIOUS))
            assert sha(PUBLISHER/member) == digest
            row.update(delivery='prior_immutable_git_file', member=member,
                url=f'https://raw.githubusercontent.com/misko/leo-tracker-reduxredux/{COMMIT}/{member}')
        else:
            if path.is_relative_to(REPO):
                member = 'source/repository/'+str(path.relative_to(REPO))
            elif path.is_relative_to(CONTROLS):
                member = 'source/previous_controls/'+str(path.relative_to(CONTROLS))
            elif path.is_relative_to(WITNESS):
                member = 'source/previous_witness/'+str(path.relative_to(WITNESS))
            elif path.is_relative_to(PREVIOUS):
                member = 'source/previous_movement/'+str(path.relative_to(PREVIOUS))
            else:
                raise ValueError('Unresolved runtime source '+str(path))
            destination = ROOT/member
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(path.read_bytes())
            assert sha(destination) == digest
            row.update(delivery='current_exact_external_source_snapshot', member=member)
            if str(path) in previous:
                row['different_from_R1_sha256'] = previous[str(path)]['sha256']
            new_external.append(row)
        files.append(row)
    dirty = set(old_inventory['actual_imported_dirty_source_snapshots'])
    result = dict(no_position_fits=True, no_GPS=True, source_sha256=sha(Path(__file__)),
        closure_scope='Scientific execution03 imports plus both safe saved-input context loads; excludes unused broad source inventories and installed third-party package sources',
        files=files, runtime_python_sources=len(files),
        total_source_bytes=sum(row['bytes'] for row in files),
        delivery_counts={kind:sum(row['delivery']==kind for row in files) for kind in sorted({row['delivery'] for row in files})},
        actual_imported_dirty_source_snapshots=[row for row in files if row['path'] in dirty],
        new_external_source_snapshots=len(new_external),
        changed_R1_imported_sources=[row for row in new_external if 'different_from_R1_sha256' in row],
        prior_report_commit=COMMIT, prior_index_sha256=sha(index_path),
        prior_runtime_source_inventory_sha256=sha(old_inventory_path),
        prior_runtime_capsule={key:capsule[key] for key in ('asset','url','bytes','sha256')},
        installed_package_versions={name:importlib.metadata.version(name) for name in ('numpy','scipy','matplotlib','sgp4','pydantic')},
        python_version=sys.version, raw_IQ_included=False, production_files_modified=False)
    with (HERE/'runtime_closure.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','actual_imported_dirty_source_snapshots')}, indent=2))


if __name__ == '__main__':
    main()
