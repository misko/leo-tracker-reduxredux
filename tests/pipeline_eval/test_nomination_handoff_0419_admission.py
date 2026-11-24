from pathlib import Path
from types import SimpleNamespace

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3.nomination_handoff_0419_admission import (
    CASE,
    HOUR_NS,
    PAIR_PIN,
    archive_roots,
    available_archive,
    enrollment,
)


def test_rank_two_retains_original_roster_pair_and_order():
    row = enrollment()
    assert (row["case"], row["rank"], row["roster_size"], row["release_pair_sha256"]) == (CASE, 2, 87, PAIR_PIN)
    assert row["planned_order"] == ["routed", "installed"]
    assert 0 < row["estimated_worker_ceiling_s"] < 120


def test_archive_census_does_not_follow_symlinked_stages_or_tle_ports(tmp_path):
    inside = tmp_path / "leo-good"
    (inside / "tle/archive/space-track").mkdir(parents=True)
    outside = tmp_path / "backing"
    (outside / "archive/space-track").mkdir(parents=True)
    (tmp_path / "leo-link").symlink_to(inside)
    link = tmp_path / "leo-link-port"
    link.mkdir()
    (link / "tle").symlink_to(outside)
    assert archive_roots((tmp_path,)) == ([inside / "tle"], [])


def test_archive_roster_deduplicates_and_excludes_cutoff_without_reading_bodies():
    capture, cutoff = 80 * HOUR_NS, 82 * HOUR_NS

    def ref(name, collected):
        return SimpleNamespace(path=Path(name), collected_utc_ns=collected,
                               sha256=name, byte_size=123)

    def reader(folder, *refs):
        return SimpleNamespace(root=Path(folder), list_snapshots=lambda _: refs)

    body = ref("earlier", capture)
    first = reader("first", ref("old", 7 * HOUR_NS), body, ref("cutoff", cutoff))
    second = reader("second", body, ref("later", cutoff + 1))
    actual = available_archive((first, second), capture, cutoff)
    assert actual["candidate_union"] == dict(sha256=canonical_digest({"earlier": "earlier"}),
                                            count=1, bytes=123, oldest_ns=capture, newest_ns=capture)
