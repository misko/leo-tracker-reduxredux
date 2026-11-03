"""Verified local directory publication with stable historical source paths.

The destination and receipt are durable before an atomic source-path exchange.
Only the invocation's receipted, retired source inode can subsequently be removed.
Callers must quiesce writers/readers that cache resolved source paths.
"""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time


def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _sync(path.parent)


def _digest(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _fingerprint(path: Path) -> tuple[int, int, int, int]:
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode):
        raise ValueError(f"archive source is not a regular file: {path}")
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def _metadata(original: Path, copy: Path) -> None:
    if os.geteuid() == 0:
        s = original.stat(follow_symlinks=False)
        os.chown(copy, s.st_uid, s.st_gid, follow_symlinks=False)
    shutil.copystat(original, copy, follow_symlinks=False)


def _inventory(root: Path) -> dict[str, tuple[int, int, int, int]]:
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            child = Path(directory) / name
            if child.is_symlink() or child.is_mount():
                raise ValueError("archive cannot follow nested directory symlinks or mounts")
        for name in files:
            path = Path(directory) / name
            result[str(path.relative_to(root))] = _fingerprint(path)
    return result


def _exchange(left: Path, right: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    function = libc.renameat2
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(-100, os.fsencode(left), -100, os.fsencode(right), 2):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


class VerifiedDirectoryArchive:
    def __init__(self, source_root: Path, archive_root: Path, *, progress=None):
        for root in (source_root, archive_root):
            if not root.is_absolute() or root.is_symlink():
                raise ValueError("archive roots must be absolute real directories")
            resolved = root.resolve()
            if resolved == Path('/mnt/qnap01') or Path('/mnt/qnap01') in resolved.parents:
                raise ValueError("QNAP is read-only and cannot participate in archival")
        source_root.mkdir(parents=True, exist_ok=True)
        archive_root.mkdir(parents=True, exist_ok=True)
        self.source = source_root.resolve()
        self.destination = archive_root.resolve()
        if self.source == self.destination or self.source in self.destination.parents or self.destination in self.source.parents:
            raise ValueError("archive roots must be disjoint")
        self.control = self.destination / '.archive-control'
        self.control.mkdir(mode=0o750, exist_ok=True)
        if self.control.is_symlink():
            raise ValueError("archive control cannot be a symlink")
        self.progress = progress or (lambda event: None)

    def archive(self, name: str) -> dict:
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', name) or name in ('.', '..'):
            raise ValueError("archive requires one safe directory name")
        token = hashlib.sha256(name.encode()).hexdigest()
        with (self.control / f'{token}.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._archive(name, token)

    def pending_names(self) -> list[str]:
        """Resume durable intents even when the source is already a link."""
        result = []
        for path in sorted(self.control.glob('*.json')):
            receipt = json.loads(path.read_bytes())
            source = Path(receipt['source'])
            if (receipt['state'] != 'complete' and source.parent == self.source
                    and receipt['target'] == str(self.destination / source.name)):
                result.append(source.name)
        return result

    def _archive(self, name: str, token: str) -> dict:
        source = self.source / name
        target = self.destination / name
        staging = self.control / f'{token}.partial'
        retired = self.source / f'.archive-retired-{token}'
        receipt_path = self.control / f'{token}.json'
        receipt = json.loads(receipt_path.read_bytes()) if receipt_path.exists() else None
        if receipt is not None and (receipt['source'] != str(source) or receipt['target'] != str(target)):
            raise ValueError("archive receipt belongs to different roots")
        if source.is_symlink():
            if source.resolve(strict=True) != target or not receipt:
                raise ValueError("source link has no matching archive receipt")
            if receipt['state'] == 'complete' and not retired.exists():
                return receipt
            self._verify(target, receipt['files'])
            return self._retire(receipt, receipt_path, retired)
        if not source.is_dir() or source.is_mount():
            raise ValueError("source must be one real, unmounted directory")
        pending_exchange = retired.is_symlink() and retired.resolve() == target and receipt is not None
        if target.is_symlink() or staging.is_symlink() or (retired.exists() and not pending_exchange):
            raise ValueError("unexpected archive staging, destination or retired path")
        snapshot = _inventory(source)
        inode = source.stat()
        if target.exists():
            if not receipt or receipt['state'] not in ('ready', 'published'):
                raise FileExistsError("destination already exists without a publication receipt")
            if (inode.st_ino, inode.st_dev) != (receipt['source_inode'], receipt['source_device']):
                raise ValueError("source directory inode changed after publication")
            self._verify(target, receipt['files'])
            if set(snapshot) != set(receipt['files']):
                raise ValueError("source file inventory changed after publication")
            for relative, entry in receipt['files'].items():
                if _digest(source / relative) != entry['sha256']:
                    raise ValueError("source changed after archive publication")
        else:
            staging.mkdir(exist_ok=True)
            prior = receipt.get('files', {}) if receipt and receipt['state'] == 'copying' else {}
            receipt = {'schema_version': 1, 'state': 'copying', 'source': str(source),
                       'target': str(target), 'source_inode': inode.st_ino,
                       'source_device': inode.st_dev, 'retired': str(retired), 'files': {}}
            _json(receipt_path, receipt)
            copied_bytes = 0
            for relative, fingerprint in sorted(snapshot.items()):
                original, copy = source / relative, staging / relative
                copy.parent.mkdir(parents=True, exist_ok=True)
                saved = prior.get(relative)
                reused = (saved and saved.get('source_fingerprint') == list(fingerprint)
                          and copy.is_file() and _digest(copy) == saved['sha256'])
                if reused:
                    entry = saved
                else:
                    temporary = copy.with_name(copy.name + '.copying')
                    hasher = hashlib.sha256()
                    fd = os.open(original, os.O_RDONLY | os.O_NOFOLLOW)
                    with os.fdopen(fd, 'rb') as src, temporary.open('wb') as dst:
                        while block := src.read(4 * 1024**2):
                            dst.write(block)
                            hasher.update(block)
                        dst.flush()
                        os.fsync(dst.fileno())
                    if _fingerprint(original) != fingerprint:
                        raise ValueError("source changed during archive copy")
                    expected = hasher.hexdigest()
                    if _digest(temporary) != expected:
                        raise ValueError("RAID copy failed SHA-256 verification")
                    _metadata(original, temporary)
                    os.replace(temporary, copy)
                    _sync(copy.parent)
                    entry = {'bytes': fingerprint[2], 'sha256': expected,
                             'source_fingerprint': list(fingerprint)}
                receipt['files'][relative] = entry
                copied_bytes += entry['bytes']
                _json(receipt_path, receipt)
                self.progress({'name': name, 'state': 'copying', 'files': len(receipt['files']),
                               'bytes': copied_bytes, 'updated_utc_ns': time.time_ns()})
            if _inventory(source) != snapshot:
                raise ValueError("source directory changed during archival")
            # Preserve empty directories too. No nested symlink was accepted.
            for directory, dirs, files in os.walk(source):
                (staging / Path(directory).relative_to(source)).mkdir(parents=True, exist_ok=True)
            for directory, dirs, files in os.walk(staging, topdown=False):
                _metadata(source / Path(directory).relative_to(staging), Path(directory))
                _sync(Path(directory))
            if set(_inventory(staging)) != set(receipt['files']):
                raise ValueError("archive staging contains unexpected files")
            if target.exists():
                raise FileExistsError(target)
            receipt['state'] = 'ready'
            _json(receipt_path, receipt)
            os.rename(staging, target)
            _sync(self.destination)
            receipt['state'] = 'published'
            _json(receipt_path, receipt)
        if _inventory(source) != snapshot:
            raise ValueError("source changed before path exchange")
        # The intended retired path is durable before this atomic exchange.
        if not pending_exchange:
            retired.symlink_to(target, target_is_directory=True)
        _exchange(source, retired)
        _sync(self.source)
        receipt['state'] = 'linked'
        _json(receipt_path, receipt)
        return self._retire(receipt, receipt_path, retired)

    def _verify(self, target: Path, entries: dict) -> None:
        actual = _inventory(target)
        if set(actual) != set(entries):
            raise ValueError("published RAID archive file inventory changed")
        for relative, entry in entries.items():
            if actual[relative][2] != entry['bytes'] or _digest(target / relative) != entry['sha256']:
                raise ValueError("published RAID archive digest changed")

    def _retire(self, receipt: dict, receipt_path: Path, retired: Path) -> dict:
        if retired.exists():
            s = retired.lstat()
            if (retired != Path(receipt['retired']) or not stat.S_ISDIR(s.st_mode)
                    or s.st_ino != receipt['source_inode'] or s.st_dev != receipt['source_device']):
                raise ValueError("refusing to remove an unrecognized retired source inode")
            shutil.rmtree(retired)
            _sync(self.source)
        receipt.update(state='complete', completed_utc_ns=time.time_ns(),
                       bytes=sum(f['bytes'] for f in receipt['files'].values()))
        _json(receipt_path, receipt)
        self.progress({'name': Path(receipt['source']).name, 'state': 'complete', 'bytes': receipt['bytes']})
        return receipt
