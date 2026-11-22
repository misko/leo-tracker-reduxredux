from types import SimpleNamespace

import pytest

from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.sky.propagation import element_line_checksum, parse_element_sets

BASE = (
    "0 STARLINK-1008\n"
    "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9992\n"
    "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260127\n"
)


def at_day(day):
    lines = BASE.splitlines()
    line = lines[1][:20] + f"{day:012.8f}" + lines[1][32:68]
    lines[1] = line + str(element_line_checksum(line))
    return "\n".join(lines) + "\n"


def test_both_collection_and_epoch_must_be_in_past():
    cutoff = parse_element_sets(at_day(233)).element_epoch_utc_ns()[0]
    snapshots = [
        SimpleNamespace(
            collected_utc_ns=cutoff + d,
            sha256=str(i),
            digest=str(i),
            provider="space-track",
            text=at_day(day),
        )
        for i, (d, day) in enumerate([(-2000, 231.9), (-1000, 232.5), (-500, 234), (100, 232.9)])
    ]

    class Reader:
        def list_snapshots(self, provider):
            return snapshots

        def read(self, snapshot):
            assert snapshot.collected_utc_ns <= cutoff
            return snapshot.text

    result = causal_catalogue(Reader(), cutoff)
    assert result.provenance[0]["snapshot_digest"] == "1"
    assert result.catalogue.element_epoch_utc_ns()[0] < cutoff
    assert result.snapshot_count == 3


def test_missing_past_archive_is_explicit():
    reader = SimpleNamespace(list_snapshots=lambda provider: [])
    with pytest.raises(ValueError, match="no past"):
        causal_catalogue(reader, 1000)


def test_equal_epoch_uses_collection_then_digest_for_complete_winning_provenance():
    text = at_day(232.5)
    epoch, = parse_element_sets(text).element_epoch_utc_ns()
    cutoff = epoch + 5_000_000_000
    snapshots = [SimpleNamespace(collected_utc_ns=epoch + collected, sha256=digest,
                                 digest="sha256:" + digest, provider="space-track",
                                 text=text.replace("STARLINK-1008", name))
                 for collected, digest, name in ((3, "a", "STARLINK-A"), (3, "z", "STARLINK-Z"),
                                                 (2, "zz", "STARLINK-OLDER"))]
    reader = SimpleNamespace(list_snapshots=lambda _: snapshots, read=lambda item: item.text)
    result = causal_catalogue(reader, cutoff)
    assert result.catalogue.names == ("STARLINK-Z",)
    assert result.provenance == (dict(norad=44714, name="STARLINK-Z", element_epoch_utc_ns=epoch,
                                      collected_utc_ns=epoch + 3, snapshot_digest="sha256:z",
                                      provider="space-track", age_s=5.),)
