"""Verified local archives that preserve absolute scientific publication paths."""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def tree_binding(root):
    entries = {}
    for path in sorted(Path(root).rglob('*')):
        name = str(path.relative_to(root))
        if path.is_symlink():
            entries[name] = dict(kind='symlink', target=os.readlink(path))
        elif path.is_file():
            with path.open('rb') as stream:
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            entries[name] = dict(kind='file', sha256=sha, bytes=path.stat().st_size)
        elif path.is_dir():
            entries[name] = dict(kind='directory')
        else:
            raise ValueError('Unsupported archive entry: ' + str(path))
    return entries


def write(path, value):
    temporary = path.with_suffix('.partial')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    temporary.replace(path)


def local(path):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('Archive paths must be canonical without parent traversal')
    if path.resolve().is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    return path


def archive_role(stage, destination, receipt_path, *, staging_root, archive_root):
    """Archive outside worker timing; interrupted/corrupt copies retain originals.

    Keep a symlink at the original absolute path because requests and public
    receipts include that path. A parked original covers the rename/link crash
    window; only a byte-verified duplicate is removed.
    """
    stage, destination, receipt_path = map(local, (stage, destination, receipt_path))
    staging_root, archive_root = map(local, (staging_root, archive_root))
    stage_root_resolved, archive_root_resolved = staging_root.resolve(), archive_root.resolve()
    if (stage_root_resolved.is_relative_to(archive_root_resolved)
            or archive_root_resolved.is_relative_to(stage_root_resolved)):
        raise ValueError('Staging and archive roots must be disjoint')
    if (not stage.parent.resolve().is_relative_to(staging_root.resolve())
            or not destination.parent.resolve().is_relative_to(archive_root.resolve())
            or stage == staging_root or destination == archive_root
            or destination.is_symlink()
            or (not stage.is_symlink() and not stage.resolve().is_relative_to(stage_root_resolved))):
        raise ValueError('Archive paths escape owned roots')
    parked = stage.with_name(stage.name + '.archive-parked')
    if (not receipt_path.resolve().is_relative_to(stage_root_resolved)
            or any(receipt_path.resolve().is_relative_to(path.resolve()) for path in (stage, parked))):
        raise ValueError('Execution receipt must remain outside the archived stage and parked original')
    receipt = json.loads(receipt_path.read_bytes())
    prior = receipt.get('archive', {})
    began = time.monotonic()

    def verify_destination():
        if not prior.get('verified') or prior.get('destination') != str(destination) or prior.get('stage') != str(stage):
            raise ValueError('Archive transition has no matching verification receipt')
        if not destination.is_dir() or digest(tree_binding(destination)) != prior['tree_sha256']:
            raise ValueError('Verified archive changed; all remaining originals retained')

    def discard_verified_parked():
        if parked.exists():
            remaining, archived = tree_binding(parked), tree_binding(destination)
            if parked.is_symlink() or any(archived.get(name) != entry for name, entry in remaining.items()):
                raise ValueError('Parked original differs; preserve it for investigation')
            shutil.rmtree(parked)

    if stage.is_symlink():
        if stage.resolve() != destination.resolve():
            raise ValueError('Stage symlink points to a different archive')
        verify_destination()
        discard_verified_parked()
        return receipt
    if not stage.exists():
        verify_destination()
        stage.symlink_to(destination, target_is_directory=True)
        discard_verified_parked()
        return receipt
    if not stage.is_dir() or parked.exists():
        raise ValueError('Unsafe or ambiguous stage; preserve every copy')
    original = tree_binding(stage)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + '.archive-partial')
    if partial.is_symlink():
        raise ValueError('Archive partial is a symlink')
    if not destination.exists():
        if not partial.exists():
            shutil.copytree(stage, partial, symlinks=True)
        if tree_binding(partial) != original:
            raise ValueError('Archive partial differs; original stage retained')
        partial.rename(destination)
    if tree_binding(destination) != original:
        raise ValueError('Archive differs; original stage retained')
    receipt['archive'] = dict(verified=True, tree_sha256=digest(original),
                              stage=str(stage), destination=str(destination),
                              bytes=sum(row.get('bytes', 0) for row in original.values()),
                              files=sum(row['kind'] == 'file' for row in original.values()),
                              wall_seconds=time.monotonic() - began)
    write(receipt_path, receipt)
    prior = receipt['archive']
    stage.rename(parked)
    stage.symlink_to(destination, target_is_directory=True)
    discard_verified_parked()
    receipt['archive']['wall_seconds'] = time.monotonic() - began
    write(receipt_path, receipt)
    return receipt


def resources_ready(stage_root, archive_root=None, *, reserve_gib=20, expected_gib=10,
                    stage_free_gib=10, archive_free_gib=10):
    fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(fields['MemAvailable'].split()[0]) / 1024 ** 2
    stage_free = shutil.disk_usage(stage_root).free / 1024 ** 3
    archive_free = shutil.disk_usage(archive_root).free / 1024 ** 3 if archive_root else None
    return dict(ready=available >= reserve_gib + expected_gib and stage_free >= stage_free_gib
                and (archive_free is None or archive_free >= archive_free_gib),
                mem_available_gib=available, stage_free_gib=stage_free,
                archive_free_gib=archive_free)
