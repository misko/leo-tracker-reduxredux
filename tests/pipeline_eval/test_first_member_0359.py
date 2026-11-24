from reports.ALGO08.v3.first_member_0359 import local_observation


def test_explicit_local_path_and_spool_alias(tmp_path, monkeypatch):
    recording = tmp_path / "original" / "run"
    segment = recording / "run-segment-00000000"
    segment.mkdir(parents=True)
    absent = tmp_path / "tmpfs"
    absent.mkdir()
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / recording.name).symlink_to(recording)

    def fail_on_metadata(*args):
        raise AssertionError("An absent path or spool alias must not open metadata")

    monkeypatch.setattr("reports.ALGO08.v3.first_member_0359.bound_index", fail_on_metadata)
    rows = local_observation(recording, segment, {}, {}, roots=(absent,), spool=spool)
    assert [row["status"] for row in rows] == ["absent", "original_alias"]
    assert rows[1]["target"] == str(recording)


def test_unrelated_spool_symlink_is_not_admitted(tmp_path):
    recording = tmp_path / "original" / "run"
    recording.mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / recording.name).symlink_to(other)
    match, = local_observation(recording, recording / "run-segment-00000000", {}, {}, roots=(), spool=spool)
    assert match["status"] == "unadmitted_alias"
