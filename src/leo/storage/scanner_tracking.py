"""Separate, immutable shared tracking products with resumable checkpoints."""

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter

from leo.contracts.digests import sha256_digest
from leo.contracts.scanner_tracking import (
    ArtifactNameV12,
    ScannerTrackingProductV1,
    ScannerTrackingProductV2,
    ScannerTrackingProductV3,
    ScannerTrackingProductV4,
    ScannerTrackingProductV5,
    ScannerTrackingProductV6,
    ScannerTrackingProductV7,
    ScannerTrackingProductV8,
    ScannerTrackingProductV9,
    ScannerTrackingProductV10,
    ScannerTrackingProductV11,
    ScannerTrackingProductV12,
    ScannerTrackingStatusV1,
    ScannerTrackingStatusV2,
    ScannerTrackingStatusV3,
    ScannerTrackingStatusV4,
    ScannerTrackingStatusV5,
    ScannerTrackingStatusV6,
    ScannerTrackingStatusV7,
    ScannerTrackingStatusV8,
    ScannerTrackingStatusV9,
    ScannerTrackingStatusV10,
    ScannerTrackingStatusV11,
    ScannerTrackingStatusV12,
    SessionId,
    TrackingArtifactV12,
)
from leo.storage.adaptive_hop_analysis import _publish, _read, _seal, _unseal
from leo.storage.pinned import PinnedLocalRoot

_LIMIT = 64 * 1024 * 1024


class ScannerTrackingStore:
    def __init__(self, root: Path, *, read_only: bool = True):
        resolved = root.resolve()
        if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
            raise ValueError("shared tracking cannot use QNAP")
        self.root, self.read_only = root, read_only

    @contextmanager
    def directory(self, session_id: str, *, create: bool = False, version: int = 12):
        TypeAdapter(SessionId).validate_python(session_id)
        if create and self.read_only:
            raise PermissionError("tracking store is read-only")
        root = PinnedLocalRoot(self.root)
        directory = None
        try:
            directory = root.child(f"scanner-shared-tracking-v{version}", session_id, create=create)
            yield directory
        finally:
            if directory is not None:
                directory.close()
            root.close()

    def status(
        self, session_id: str
    ) -> (
        ScannerTrackingStatusV12
        | ScannerTrackingStatusV11
        | ScannerTrackingStatusV10
        | ScannerTrackingStatusV9
        | ScannerTrackingStatusV8
        | ScannerTrackingStatusV7
        | ScannerTrackingStatusV6
        | ScannerTrackingStatusV5
        | ScannerTrackingStatusV4
        | ScannerTrackingStatusV3
        | ScannerTrackingStatusV2
        | ScannerTrackingStatusV1
    ):
        current = self._status_v12(session_id)
        if current.state != "pending":
            return current
        current_v11 = self._status_v11(session_id)
        if current_v11.state != "pending":
            return current_v11
        current_v10 = self._status_v10(session_id)
        if current_v10.state != "pending":
            return current_v10
        current_v9 = self._status_v9(session_id)
        if current_v9.state != "pending":
            return current_v9
        current_v8 = self._status_v8(session_id)
        if current_v8.state != "pending":
            return current_v8
        current_v7 = self._status_v7(session_id)
        if current_v7.state != "pending":
            return current_v7
        current_v6 = self._status_v6(session_id)
        if current_v6.state != "pending":
            return current_v6
        current_v5 = self._status_v5(session_id)
        if current_v5.state != "pending":
            return current_v5
        current_v4 = self._status_v4(session_id)
        if current_v4.state != "pending":
            return current_v4
        current_v3 = self._status_v3(session_id)
        if current_v3.state != "pending":
            return current_v3
        current_v2 = self._status_v2(session_id)
        if current_v2.state != "pending":
            return current_v2
        legacy = self._status_v1(session_id)
        if (
            legacy.state == "complete"
            and legacy.product is not None
            and legacy.product.trajectory_state == "unsupported"
            and any("qualified UTC timing authority" in reason for reason in legacy.product.reasons)
        ):
            return current
        return legacy if legacy.state != "pending" else current

    def analysis_status(self, session_id: str) -> ScannerTrackingStatusV12:
        """Return only the current analysis version's state for queue workers.

        Public readers retain the newest published historical product while a
        newer analysis version is pending.  Workers must instead see that
        pending V12 state so an intentional policy revision is actually run.
        """
        return self._status_v12(session_id)

    def _status_v12(self, session_id: str) -> ScannerTrackingStatusV12:
        try:
            with self.directory(session_id, version=12) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV12
                    )
                    return ScannerTrackingStatusV12(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV12
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV12(session_id=session_id)
        except FileNotFoundError:
            return ScannerTrackingStatusV12(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV12(session_id=session_id)
            raise

    def _status_v11(self, session_id: str) -> ScannerTrackingStatusV11:
        try:
            with self.directory(session_id, version=11) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV11
                    )
                    return ScannerTrackingStatusV11(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV11
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV11(session_id=session_id)
        except FileNotFoundError:
            return ScannerTrackingStatusV11(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV11(session_id=session_id)
            raise

    def _status_v10(self, session_id: str) -> ScannerTrackingStatusV10:
        try:
            with self.directory(session_id, version=10) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV10
                    )
                    return ScannerTrackingStatusV10(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV10
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV10(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV10(session_id=session_id)
            raise

    def _status_v9(self, session_id: str) -> ScannerTrackingStatusV9:
        try:
            with self.directory(session_id, version=9) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV9
                    )
                    return ScannerTrackingStatusV9(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV9
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV9(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV9(session_id=session_id)
            raise

    def _status_v8(self, session_id: str) -> ScannerTrackingStatusV8:
        try:
            with self.directory(session_id, version=8) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV8
                    )
                    return ScannerTrackingStatusV8(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    return ScannerTrackingStatusV8(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV8(session_id=session_id)
            raise

    def _status_v7(self, session_id: str) -> ScannerTrackingStatusV7:
        try:
            with self.directory(session_id, version=7) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV7
                    )
                    return ScannerTrackingStatusV7(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV7
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV7(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV7(session_id=session_id)
            raise

    def _status_v6(self, session_id: str) -> ScannerTrackingStatusV6:
        try:
            with self.directory(session_id, version=6) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV6
                    )
                    return ScannerTrackingStatusV6(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV6
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV6(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV6(session_id=session_id)
            raise

    def _status_v5(self, session_id: str) -> ScannerTrackingStatusV5:
        try:
            with self.directory(session_id, version=5) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV5
                    )
                    return ScannerTrackingStatusV5(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV5
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV5(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV5(session_id=session_id)
            raise

    def _status_v4(self, session_id: str) -> ScannerTrackingStatusV4:
        try:
            with self.directory(session_id, version=4) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV4
                    )
                    return ScannerTrackingStatusV4(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV4
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV4(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV4(session_id=session_id)
            raise

    def _status_v3(self, session_id: str) -> ScannerTrackingStatusV3:
        try:
            with self.directory(session_id, version=3) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV3
                    )
                    return ScannerTrackingStatusV3(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        return _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV3
                        )
                    except FileNotFoundError:
                        return ScannerTrackingStatusV3(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV3(session_id=session_id)
            raise

    def _status_v2(self, session_id: str) -> ScannerTrackingStatusV2:
        try:
            with self.directory(session_id) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV2
                    )
                    result = ScannerTrackingStatusV2(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        result = _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV2
                        )
                    except FileNotFoundError:
                        result = ScannerTrackingStatusV2(session_id=session_id)
                if result.session_id != session_id or (
                    result.product and result.product.session_id != session_id
                ):
                    raise ValueError("tracking session binding differs")
                return result
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV2(session_id=session_id)
            raise

    def _status_v1(self, session_id: str) -> ScannerTrackingStatusV1:
        try:
            with self.directory(session_id, version=1) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV1
                    )
                    return ScannerTrackingStatusV1(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    return ScannerTrackingStatusV1(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV1(session_id=session_id)
            raise

    def save(self, status: ScannerTrackingStatusV12) -> None:
        status = ScannerTrackingStatusV12.model_validate(status.model_dump())
        with self.directory(status.session_id, create=True) as directory:
            try:
                _read(directory, "manifest.json", _LIMIT)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("tracking publication is already immutable")
            temporary = f".checkpoint-{uuid4().hex}"
            _publish(directory, temporary, _seal(status), _LIMIT)
            os.replace(
                temporary,
                "checkpoint.json",
                src_dir_fd=directory.fileno(),
                dst_dir_fd=directory.fileno(),
            )
            os.fsync(directory.fileno())

    def put_artifact(
        self, session_id: str, name: ArtifactNameV12, payload: bytes
    ) -> TrackingArtifactV12:
        TypeAdapter(ArtifactNameV12).validate_python(name)
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("tracking artifact is not PNG")
        reference = TrackingArtifactV12(
            name=name, sha256=sha256_digest(payload), byte_count=len(payload)
        )
        with self.directory(session_id, create=True) as directory:
            try:
                old = _read(directory, name + ".png", _LIMIT)
            except FileNotFoundError:
                _publish(directory, name + ".png", payload, _LIMIT)
            else:
                if old != payload:
                    raise ValueError("tracking artifact is immutable")
        return reference

    def publish(self, product: ScannerTrackingProductV12) -> None:
        product = ScannerTrackingProductV12.model_validate(product.model_dump())
        if product.position_diagnostic is None:
            raise ValueError("cannot finalize tracking without a position diagnostic")
        if product.tle_state == "pending":
            raise ValueError("cannot finalize pending TLE comparisons")
        with self.directory(product.session_id, create=True) as directory:
            for ref in product.artifacts:
                payload = _read(directory, ref.name + ".png", _LIMIT)
                if len(payload) != ref.byte_count or sha256_digest(payload) != ref.sha256:
                    raise ValueError("tracking artifact digest differs")
            payload = _seal(product)
            try:
                previous = _read(directory, "manifest.json", _LIMIT)
            except FileNotFoundError:
                _publish(directory, "manifest.json", payload, _LIMIT)
            else:
                if previous != payload:
                    raise ValueError("tracking publication is immutable")

    def artifact(self, session_id: str, name: ArtifactNameV12) -> bytes | None:
        TypeAdapter(ArtifactNameV12).validate_python(name)
        product = self.status(session_id).product
        ref = next((r for r in product.artifacts if r.name == name), None) if product else None
        if ref is None:
            return None
        assert product is not None
        with self.directory(
            session_id,
            version=12
            if product.analysis_id == "scanner-shared-tracking-v12"
            else 11
            if product.analysis_id == "scanner-shared-tracking-v11"
            else 10
            if product.analysis_id == "scanner-shared-tracking-v10"
            else 9
            if product.analysis_id == "scanner-shared-tracking-v9"
            else 8
            if product.analysis_id == "scanner-shared-tracking-v8"
            else 7
            if product.analysis_id == "scanner-shared-tracking-v7"
            else 6
            if product.analysis_id == "scanner-shared-tracking-v6"
            else 5
            if product.analysis_id == "scanner-shared-tracking-v5"
            else 4
            if product.analysis_id == "scanner-shared-tracking-v4"
            else 3
            if product.analysis_id == "scanner-shared-tracking-v3"
            else (2 if product.analysis_id == "scanner-shared-tracking-v2" else 1),
        ) as directory:
            payload = _read(directory, name + ".png", _LIMIT)
        if len(payload) != ref.byte_count or sha256_digest(payload) != ref.sha256:
            raise ValueError("tracking artifact digest differs")
        return payload
