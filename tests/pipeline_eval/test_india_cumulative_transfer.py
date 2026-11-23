from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def transfer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import india_cumulative_transfer

    return india_cumulative_transfer


def test_signed_stock_check_binds_satellite_roles_and_numerical_evidence(transfer):
    before = dict(selected_rows={"c0": [[1, 42, "predictive"]]}, science={"grid": "A"})
    transfer.signed_stock_match(before, dict(before))
    with pytest.raises(ValueError, match="selected_rows"):
        transfer.signed_stock_match(before, before | {"selected_rows": {}})
    with pytest.raises(ValueError, match="science"):
        transfer.signed_stock_match(before, before | {"science": {"grid": "B"}})


def test_numerical_handoff_rejects_a_live_recording_or_modified_offer(transfer, tmp_path):
    args = SimpleNamespace(recording=tmp_path / "missing", archive=tmp_path / "tle",
                           output=tmp_path)
    region = SimpleNamespace(document=lambda: {"center": [20.0, 30.0]})
    identity = dict(offer=region.document())

    def check(offer=region, archive=args.archive):
        transfer.verify_authority(args.recording, args.output, archive, offer, args, identity)

    check()
    with pytest.raises(ValueError, match="original offer"):
        check(offer=SimpleNamespace(document=lambda: {"center": [21.0, 30.0]}))
    with pytest.raises(ValueError, match="original offer"):
        check(archive=Path("/other-causal-archive"))
    args.recording.touch()
    with pytest.raises(ValueError, match="saved waveform packet"):
        check()


def test_libraries_are_byte_pinned(transfer, tmp_path):
    path = tmp_path / "native.so"
    path.write_bytes(b"reference")
    assert transfer.checked(path, transfer.digest(b"reference")) == b"reference"
    with pytest.raises(ValueError, match="pinned library changed"):
        transfer.checked(path, transfer.digest(b"substitute"))
