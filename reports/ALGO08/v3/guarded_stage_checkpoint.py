"""Verify signed staged extents and recover the last sealed local prefix."""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile


EMPTY_PIN = "sha256:" + sha256().hexdigest()


@dataclass(frozen=True)
class Extent:
    relative: Path
    size: int
    sha256: str

    def __post_init__(self):
        if (self.relative.is_absolute() or len(self.relative.parts) != 2 or ".." in self.relative.parts
                or self.size < 1 or not valid_pin(self.sha256)):
            raise ValueError("Expected a two-level, signed regular member")


@dataclass(frozen=True)
class Partial:
    extent: Extent
    offset: int
    checksum: object
    source_identity: tuple | None


def valid_pin(value):
    return (isinstance(value, str) and len(value) == 71 and value.startswith("sha256:")
            and all(c in "0123456789abcdef" for c in value[7:]))


@contextmanager
def staging_lock(path):
    with path.open("ab") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another DS30-0016 staging worker owns the exclusive lock") from error
        yield


def identity(metadata):
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns


def checked_local(path, size, pin):
    with path.open("rb") as stream:
        original = os.fstat(stream.fileno())
        if not stat.S_ISREG(original.st_mode) or original.st_size != size:
            raise ValueError(f"Staged extent changed: {path}")
        digest = file_digest(stream, "sha256")
        if identity(original) != identity(os.fstat(stream.fileno())):
            raise ValueError(f"Staged file changed during verification: {path}")
    if "sha256:" + digest.hexdigest() != pin:
        raise ValueError(f"Staged signed bytes or checkpoint prefix changed: {path}")
    return digest


def checkpoint(extent, member_identity, prefixes):
    return dict(relative=extent.relative.as_posix(), size=extent.size, sha256=extent.sha256,
                source_identity=member_identity, prefixes=prefixes)


def write_checkpoint(path, document):
    # The old and proposed lengths cover interruption on either side of the
    # append. Any other local length or digest fails admission.
    with NamedTemporaryFile(mode="w", dir=path.parent, prefix=".copy-checkpoint-", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(document, stream, sort_keys=True)
    os.replace(temporary, path)


def verified_extents(staged, extents, active=None):
    enrolled = {extent.relative: extent for extent in extents}
    if len(enrolled) != len(extents):
        raise ValueError("Duplicate signed extent")
    active_extent, source_identity, saved = None, None, {}
    if active is not None:
        active_extent = enrolled.get(Path(active["relative"]))
        if active_extent is None or (active["size"], active["sha256"]) != (active_extent.size, active_extent.sha256):
            raise ValueError("Checkpoint is bound to a different signed member")
        if active["source_identity"] is not None:
            source_identity = tuple(active["source_identity"])
            if len(source_identity) != 5 or source_identity[2] != active_extent.size:
                raise ValueError("Checkpoint has an invalid source identity")
        saved = dict(active["prefixes"])
        if (not 1 <= len(saved) <= 2 or any(
                type(size) is not int or not 0 <= size <= active_extent.size or not valid_pin(pin)
                for size, pin in saved.items())):
            raise ValueError("Checkpoint has invalid prefix extents")
    completed, partial = set(), None
    for relative, extent in enrolled.items():
        target = staged / relative
        if target.resolve() != target:
            raise ValueError(f"Staged signed member path is redirected: {target}")
        if not target.exists():
            if extent == active_extent:
                if saved.get(0) != EMPTY_PIN:
                    raise ValueError("Local checkpointed member disappeared")
                partial = Partial(extent, 0, sha256(), source_identity)
            continue
        metadata = target.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"Staged signed member is not a regular file: {target}")
        current = metadata.st_size
        if current == extent.size:
            checked_local(target, current, extent.sha256)
            completed.add(relative)
        elif extent == active_extent and current in saved:
            digest = checked_local(target, current, saved[current])
            partial = Partial(extent, current, digest, source_identity)
        else:
            raise ValueError(f"Local partial member has no matching sealed checkpoint: {target}")
    return completed, partial
