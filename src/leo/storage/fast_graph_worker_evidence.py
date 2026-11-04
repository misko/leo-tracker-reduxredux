"""Public diagnostic export of a fully validated graph-position worker result.

All graph-position versions expose a terminal receipt. This adapter owns the
conversion from that receipt into a complete, immutable diagnostic snapshot;
comparison tools do not construct storage namespaces or job output paths.
"""
import json
import shutil
from pathlib import Path

from leo.storage.fast_graph_position import sha
from leo.storage.uri import confined_path


def export_worker_evidence(store, job, destination):
    terminal, receipt = store.terminal(job)
    if terminal['state'] != 'complete':
        raise ValueError('Only completed graph workers can be exported')
    source = confined_path(store.root, Path(receipt['path']).parent, must_exist=True)
    target = Path(destination).resolve()
    if (target.is_relative_to('/mnt/qnap01') or target.is_relative_to(store.root)
            or store.root.is_relative_to(target)):
        raise ValueError('New local evidence export separate from the source store required')
    target.mkdir(parents=True, mode=0o700, exist_ok=False)
    files = {}
    originals = {}
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('Worker evidence cannot contain symbolic links')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Worker evidence must contain only regular files')
        relative = path.relative_to(source)
        before = sha(path)
        copy = target/'worker'/relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copy)
        if sha(path) != before or sha(copy) != before:
            raise ValueError('Worker evidence changed while copying')
        files[str(Path('worker')/relative)] = before
        originals[str(relative)] = before
    current = {}
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('Worker evidence acquired a symbolic link')
        if path.is_file():
            current[str(path.relative_to(source))] = sha(path)
    again, binding = store.terminal(job)
    if current != originals or again != terminal or binding != receipt:
        raise ValueError('Worker evidence changed during export')
    if files.get('worker/terminal.json') != receipt['sha256']:
        raise ValueError('Exported terminal differs from its verified binding')
    descriptor = dict(schema_version=1, kind='fast-graph-worker-evidence',
                      input_sha256=job['input_sha256'], model_version=job['model_version'],
                      job_id=job['job_id'], source_worker_root=str(source),
                      source_store_root=str(store.root),
                      terminal_receipt=receipt, files=files)
    with (target/'descriptor.json').open('x') as stream:
        json.dump(descriptor, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return descriptor
