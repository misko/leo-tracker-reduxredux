from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.states import RadioTransport
from leo.station import pinned_loader as loader_module
from leo.station.authority import (
    FixturePathAuthorityV1,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.station.pinned_loader import (
    AuthorityDocumentError,
    PinnedAuthorityJsonLoader,
    PinnedStationAuthorityReader,
    require_owner_uid,
)

from .manifest_examples import manifest_example, verified_digest

_CONTENT_DIGEST = f"sha256:{'4' * 64}"


def _topology(endpoint: str = "ip:192.0.2.10") -> StationReceiverTopologyV1:
    radio = StationRadioTopologyV1.create(
        radio_id="radio-a",
        radio_serial="serial-a",
        endpoint_evidence=RadioEndpointEvidenceV1(
            transport=RadioTransport.IIO_IP,
            endpoint=endpoint,
            evidence_uri="authority/radio-a.json",
            evidence_digest=_CONTENT_DIGEST,
        ),
        receiver_assignments=(
            StationReceiverAssignmentV1(
                receiver_id=0,
                physical_receiver_id="physical-a-rx0",
                hardware_epoch_external_id="hardware-a-rx0-v1",
                valid_from_utc_ns=1_000,
                valid_until_utc_ns=2_000,
            ),
            StationReceiverAssignmentV1(
                receiver_id=1,
                physical_receiver_id="physical-a-rx1",
                hardware_epoch_external_id="hardware-a-rx1-v1",
                valid_from_utc_ns=1_000,
                valid_until_utc_ns=2_000,
            ),
        ),
    )
    return StationReceiverTopologyV1.create(
        station_id="station-a",
        topology_revision="topology-v1",
        valid_from_utc_ns=1_000,
        valid_until_utc_ns=2_000,
        radios=(radio,),
    )


def _fixture() -> FixturePathAuthorityV1:
    manifest = manifest_example(radio_count=1, applied_receiver_ids=(0, 1))
    return FixturePathAuthorityV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )


def _prepare_root(tmp_path: Path) -> Path:
    root = tmp_path / "authority"
    root.mkdir(mode=0o750)
    root.chmod(0o750)
    return root


def _publish(root: Path, relative_path: str, document: object) -> tuple[Path, str]:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    for directory in (target.parent, *target.parents):
        if directory == root.parent:
            break
        directory.chmod(0o750)
        if directory == root:
            break
    payload = canonical_json_bytes(document)
    target.write_bytes(payload)
    target.chmod(0o440)
    return target, sha256_digest(payload)


def _loader(root: Path) -> PinnedAuthorityJsonLoader:
    return PinnedAuthorityJsonLoader(
        root,
        ownership_validator=require_owner_uid(os.getuid()),
    )


def test_typed_reader_loads_digest_pinned_topology_and_fixture(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    topology = _topology()
    fixture = _fixture()
    _topology_path, topology_file_digest = _publish(
        root, "station/topology.json", topology.model_dump(mode="json")
    )
    _fixture_path, fixture_file_digest = _publish(
        root, "fixtures/trial-132.json", fixture.model_dump(mode="json")
    )

    loader = _loader(root)
    reader = PinnedStationAuthorityReader(loader)
    try:
        assert (
            reader.read_topology(
                "station/topology.json", expected_file_digest=topology_file_digest
            )
            == topology
        )
        assert (
            reader.read_fixture_authority(
                "fixtures/trial-132.json", expected_file_digest=fixture_file_digest
            )
            == fixture
        )
    finally:
        loader.close()


def test_double_slash_qnap_is_rejected_before_any_open_syscall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[object] = []

    def forbidden_open(*args: object, **_kwargs: object) -> int:
        opened.append(args)
        raise AssertionError("filesystem syscall occurred before lexical QNAP rejection")

    monkeypatch.setattr(loader_module.os, "open", forbidden_open)
    with pytest.raises(ValueError, match="QNAP"):
        PinnedAuthorityJsonLoader(
            "//mnt//qnap01/authority",
            ownership_validator=require_owner_uid(os.getuid()),
        )
    assert opened == []


@pytest.mark.parametrize("symlink_parent", [False, True])
def test_loader_never_follows_document_or_component_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symlink_parent: bool,
) -> None:
    root = _prepare_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o750)
    outside.chmod(0o750)
    outside_file, file_digest = _publish(
        outside, "topology.json", _topology("ip:203.0.113.99").model_dump(mode="json")
    )
    if symlink_parent:
        (root / "station").symlink_to(outside, target_is_directory=True)
        relative = "station/topology.json"
    else:
        (root / "station").mkdir(mode=0o750)
        (root / "station").chmod(0o750)
        (root / "station" / "topology.json").symlink_to(outside_file)
        relative = "station/topology.json"

    opened_inodes: list[tuple[int, int]] = []
    real_open = os.open

    def observed_open(*args: object, **kwargs: object) -> int:
        descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
        metadata = os.fstat(descriptor)
        opened_inodes.append((metadata.st_dev, metadata.st_ino))
        return descriptor

    monkeypatch.setattr(loader_module.os, "open", observed_open)
    loader = _loader(root)
    try:
        with pytest.raises(AuthorityDocumentError, match="symlinked"):
            loader.load_contract(
                relative,
                expected_file_digest=file_digest,
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        loader.close()
    outside_identity = (outside_file.stat().st_dev, outside_file.stat().st_ino)
    assert outside_identity not in opened_inodes


def test_pinned_loader_survives_root_path_swap_without_reading_retarget(
    tmp_path: Path,
) -> None:
    root = _prepare_root(tmp_path)
    retained_topology = _topology()
    _target, retained_digest = _publish(
        root, "station/topology.json", retained_topology.model_dump(mode="json")
    )
    loader = _loader(root)

    retained = tmp_path / "retained"
    alternate = tmp_path / "alternate"
    root.rename(retained)
    alternate.mkdir(mode=0o750)
    alternate.chmod(0o750)
    _publish(
        alternate,
        "station/topology.json",
        _topology("ip:203.0.113.77").model_dump(mode="json"),
    )
    root.symlink_to(alternate, target_is_directory=True)
    try:
        observed = loader.load_contract(
            "station/topology.json",
            expected_file_digest=retained_digest,
            contract_type=StationReceiverTopologyV1,
        )
        assert observed == retained_topology
    finally:
        loader.close()


def test_loader_rejects_symlinked_root_at_initial_open(tmp_path: Path) -> None:
    outside = _prepare_root(tmp_path)
    alias = tmp_path / "authority-alias"
    alias.symlink_to(outside, target_is_directory=True)

    with pytest.raises(AuthorityDocumentError, match="symlinked component"):
        _loader(alias)


def test_loader_rechecks_root_and_component_directory_modes(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    _target, digest = _publish(
        root, "station/topology.json", _topology().model_dump(mode="json")
    )
    loader = _loader(root)
    root.chmod(0o770)
    try:
        with pytest.raises(AuthorityDocumentError, match="unsafe permissions"):
            loader.load_contract(
                "station/topology.json",
                expected_file_digest=digest,
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        loader.close()

    root.chmod(0o750)
    loader = _loader(root)
    (root / "station").chmod(0o770)
    try:
        with pytest.raises(AuthorityDocumentError, match="unsafe permissions"):
            loader.load_contract(
                "station/topology.json",
                expected_file_digest=digest,
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        loader.close()


def test_closed_loader_cannot_be_revived_by_descriptor_reuse(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    _path, digest = _publish(
        root, "topology.json", _topology().model_dump(mode="json")
    )
    loader = _loader(root)
    original_descriptor = loader._fd  # noqa: SLF001
    loader.close()
    source = os.open("/dev/null", os.O_RDONLY)
    reused = os.dup2(source, original_descriptor)
    if source != reused:
        os.close(source)
    try:
        assert reused == original_descriptor
        with pytest.raises(RuntimeError, match="closed"):
            loader.load_contract(
                "topology.json",
                expected_file_digest=digest,
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        os.close(reused)


def test_loader_rejects_file_retarget_against_expected_digest(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    target, original_digest = _publish(
        root, "topology.json", _topology().model_dump(mode="json")
    )
    loader = _loader(root)
    try:
        target.unlink()
        _publish(
            root,
            "topology.json",
            _topology("ip:203.0.113.55").model_dump(mode="json"),
        )
        with pytest.raises(AuthorityDocumentError, match="digest mismatch"):
            loader.load_contract(
                "topology.json",
                expected_file_digest=original_digest,
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        loader.close()


def test_loader_rejects_hardlinks_writable_modes_and_wrong_owner_policy(
    tmp_path: Path,
) -> None:
    root = _prepare_root(tmp_path)
    target, digest = _publish(
        root, "topology.json", _topology().model_dump(mode="json")
    )
    hardlink = root / "topology-hardlink.json"
    os.link(target, hardlink)
    loader = _loader(root)
    try:
        with pytest.raises(AuthorityDocumentError, match="exactly one hard link"):
            loader.load_contract(
                "topology.json",
                expected_file_digest=digest,
                contract_type=StationReceiverTopologyV1,
            )
        hardlink.unlink()
        target.chmod(0o640)
        with pytest.raises(AuthorityDocumentError, match="unsafe permissions"):
            loader.load_contract(
                "topology.json",
                expected_file_digest=digest,
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        loader.close()

    with pytest.raises(AuthorityDocumentError, match="unapproved owner"):
        PinnedAuthorityJsonLoader(
            root,
            ownership_validator=require_owner_uid(os.getuid() + 1),
        )


def test_loader_detects_changed_readback_even_with_same_length(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _prepare_root(tmp_path)
    _target, digest = _publish(
        root, "topology.json", _topology().model_dump(mode="json")
    )
    loader = _loader(root)
    real_pread = os.pread
    calls = 0

    def changed_readback(descriptor: int, length: int, offset: int) -> bytes:
        nonlocal calls
        data = real_pread(descriptor, length, offset)
        calls += 1
        if calls == 2:
            return data[:-1] + bytes([data[-1] ^ 1])
        return data

    monkeypatch.setattr(loader_module.os, "pread", changed_readback)
    try:
        with pytest.raises(AuthorityDocumentError, match="changed during readback"):
            loader.load_contract(
                "topology.json",
                expected_file_digest=digest,
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        loader.close()


def test_loader_rejects_duplicate_json_keys_and_oversized_documents(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    duplicate = root / "duplicate.json"
    payload = b'{"schema_version":1,"schema_version":1}'
    duplicate.write_bytes(payload)
    duplicate.chmod(0o440)
    loader = _loader(root)
    try:
        with pytest.raises(AuthorityDocumentError, match="repeats key"):
            loader.load_contract(
                "duplicate.json",
                expected_file_digest=sha256_digest(payload),
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        loader.close()

    oversized_root = tmp_path / "oversized-authority"
    shutil.copytree(root, oversized_root)
    oversized_root.chmod(0o750)
    oversized = oversized_root / "large.json"
    oversized.write_bytes(b"{" + b" " * 256 + b"}")
    oversized.chmod(0o440)
    bounded = PinnedAuthorityJsonLoader(
        oversized_root,
        ownership_validator=require_owner_uid(os.getuid()),
        max_document_bytes=128,
    )
    try:
        with pytest.raises(AuthorityDocumentError, match="bounded JSON size"):
            bounded.load_contract(
                "large.json",
                expected_file_digest=sha256_digest(oversized.read_bytes()),
                contract_type=StationReceiverTopologyV1,
            )
    finally:
        bounded.close()
