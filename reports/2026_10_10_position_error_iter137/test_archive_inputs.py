import io
import tarfile

import pytest
from archive_inputs import digest, restore


def test_restore_preserves_existing_and_rejects_overwrite(tmp_path):
    path = tmp_path / "inputs.tar.gz"
    data = b'{"physical":true}'
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("selected/DS16-001.json")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    manifest = dict(
        archive_sha256=digest(path.read_bytes()),
        files={"selected/DS16-001.json": dict(bytes=len(data), sha256=digest(data))},
    )
    destination = tmp_path / "restored"
    restore(path, manifest, destination)
    restore(path, manifest, destination)
    output = destination / "selected/DS16-001.json"
    output.write_bytes(b"different")
    with pytest.raises(ValueError, match="refuse overwrite"):
        restore(path, manifest, destination)
    assert output.read_bytes() == b"different"
