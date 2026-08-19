"""Retained no-follow capability for one pre-created local storage root."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

_QNAP = Path("/mnt/qnap01")


class PinnedLocalRoot:
    """Anchor filesystem work to an opened directory inode, not a mutable pathname."""

    def __init__(self, root: Path) -> None:
        normalized = Path(os.path.normpath(os.fspath(root)))
        if not normalized.is_absolute() or normalized == _QNAP or _QNAP in normalized.parents:
            raise ValueError("pinned storage root must be absolute local storage")
        self.root = normalized
        self._fd = _open_directory_chain(normalized)
        info = os.fstat(self._fd)
        self.identity = (info.st_dev, info.st_ino)

    @classmethod
    def _from_fd(cls, root: Path, descriptor: int) -> PinnedLocalRoot:
        value = cls.__new__(cls)
        value.root = root
        value._fd = descriptor
        info = os.fstat(descriptor)
        value.identity = (info.st_dev, info.st_ino)
        return value

    def clone(self) -> PinnedLocalRoot:
        """Return an independently owned reference to the same directory inode."""

        self.assert_open()
        return self._from_fd(self.root, os.dup(self._fd))

    @property
    def io_root(self) -> Path:
        self.assert_open()
        return Path(f"/proc/self/fd/{self._fd}")

    def assert_open(self) -> None:
        if self._fd < 0:
            raise RuntimeError("pinned storage root is closed")
        info = os.fstat(self._fd)
        if (info.st_dev, info.st_ino) != self.identity:
            raise RuntimeError("pinned storage root identity changed")

    def fileno(self) -> int:
        self.assert_open()
        return self._fd

    def child(self, *components: str, create: bool = False) -> PinnedLocalRoot:
        """Open and retain a no-follow child directory capability."""

        self.assert_open()
        descriptor = os.dup(self._fd)
        try:
            for component in components:
                if not component or component in {".", ".."} or "/" in component:
                    raise ValueError("pinned directory component is unsafe")
                if create:
                    with suppress(FileExistsError):
                        os.mkdir(component, mode=0o750, dir_fd=descriptor)
                try:
                    next_descriptor = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                except OSError as error:
                    raise ValueError(
                        f"pinned storage child is inaccessible or symlinked: {component}"
                    ) from error
                os.close(descriptor)
                descriptor = next_descriptor
        except Exception:
            os.close(descriptor)
            raise
        return self._from_fd(self.root.joinpath(*components), descriptor)

    def close(self) -> None:
        if self._fd >= 0:
            descriptor = self._fd
            self._fd = -1
            os.close(descriptor)

    def __del__(self) -> None:
        descriptor = getattr(self, "_fd", -1)
        if descriptor >= 0:
            os.close(descriptor)


def _open_directory_chain(path: Path) -> int:
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            try:
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError as error:
                raise ValueError(
                    f"pinned storage root contains an inaccessible or symlink component: "
                    f"{component}"
                ) from error
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise
