"""Import-only recovery source closure inventory; no inference or geographic reports."""
import hashlib
import json
from pathlib import Path
import sys

import recovery
import repair01
import eligibility02
import diagnostics
import report_native03

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
CONTROLS=Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(path):
    if path.is_relative_to(REPO):return 'source/repository/'+str(path.relative_to(REPO))
    if path.is_relative_to(CONTROLS):return 'source/previous_study/'+str(path.relative_to(CONTROLS))
    witness=Path('/srv/bulk/leo/research/ds24-receiver-shift-witness-20261025')
    if path.is_relative_to(witness):return 'source/previous_witness/'+str(path.relative_to(witness))
    dependency=Path('/tmp/algo03-feasible-deps')
    if path.is_relative_to(dependency):return 'source/feasible_deps/'+str(path.relative_to(dependency))
    raise ValueError('Unexpected external runtime source: '+str(path))


def main():
    movement=json.loads((ROOT/'movement/source_manifest.json').read_text())
    paths={Path(row['path']).resolve() for row in movement}
    recovery_paths=set()
    for module in tuple(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if filename:
            p=Path(filename).resolve()
            if p.suffix=='.py' and (p.is_relative_to(REPO/'src') or p.is_relative_to(REPO/'tools') or
                p.is_relative_to(CONTROLS) or p.is_relative_to(Path('/tmp/algo03-feasible-deps'))):
                recovery_paths.add(p)
    paths.update(recovery_paths)
    # Current study files are copied directly with the compact report, not duplicated.
    paths={p for p in paths if not p.is_relative_to(ROOT) and p.suffix=='.py'}
    files=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size,member=member(p)) for p in sorted(paths)]
    dirty=json.loads((ROOT/'preflight.json').read_text())['tracked_status']
    dirty={str(REPO/line[3:]) for line in dirty.splitlines()}
    output=dict(no_position_fits=True,no_GPS=True,source_sha256=sha(Path(__file__)),
        movement_import_bound_sources=len(movement),recovery_imported_sources=len(recovery_paths),
        external_runtime_sources=len(files),total_source_bytes=sum(row['bytes'] for row in files),
        actual_imported_dirty_source_snapshots=[row['path'] for row in files if row['path'] in dirty],
        scope='Union of movement prefit runtime binding and recovery entrypoint imports; excludes unused broad recovery source glob',
        broad_recovery_inventory='recovery/protocol.json retains all original source hashes for provenance',files=files)
    destination=HERE/'runtime_source_inventory.json'
    with destination.open('x') as stream:json.dump(output,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k!='files'},indent=2))


if __name__=='__main__':main()
