from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from causal_body_election import LatestBodies, RegionalRows


@dataclass(frozen=True)
class Snapshot:
    collected_utc_ns: int
    sha256: str


@dataclass(frozen=True)
class Catalogue:
    names: tuple
    satellite_numbers: tuple
    satellites: tuple
    epochs: tuple

    def __len__(self):
        return len(self.names)


class Reader:
    def __init__(self, refs, *, corrupt=None):
        self.refs, self.corrupt, self.reads = refs, corrupt, []

    def list_snapshots(self, provider):
        assert provider == "space-track"
        return self.refs

    def read(self, ref):
        self.reads.append(ref)
        if ref is self.corrupt:
            raise ValueError("wrong body digest")
        return ref.sha256


def test_dominated_read_and_parser_still_execute_and_equal_stamp_keeps_tie():
    refs = [Snapshot(stamp, key) for stamp, key in ((2, "a"), (2, "b"), (4, "a"), (4, "a"), (6, "a"))]
    cat = Catalogue(("STARLINK",), (1,), (("original", "pair"),), (1,))
    reader = Reader(refs)
    port = LatestBodies(reader, 5)
    counts, parsed = Counter(), []

    def parse(text):
        parsed.append(text)
        return cat

    select = port.parser(parse, Catalogue, counts)
    assert port.list_snapshots("space-track") == tuple(refs)
    assert [len(select(port.read(ref))) for ref in refs[:-1]] == [0, 1, 1, 1]
    assert reader.reads == refs[:-1] and parsed == ["a", "b", "a", "a"]
    assert counts["dominated_latest_rows"] == 1


def test_dominated_corrupt_reference_is_still_rejected():
    old, latest = Snapshot(2, "a"), Snapshot(4, "a")
    reader = Reader([old, latest], corrupt=old)
    port = LatestBodies(reader, 5)
    with pytest.raises(ValueError, match="wrong body digest"):
        port.read(old)
    assert reader.reads == [old]


def test_projection_preserves_repeated_norads_order_and_original_pair_objects():
    pairs = tuple(tuple([i]) for i in range(4))
    cat = Catalogue(("a", "b", "c", "d"), (7, 3, 7, 5), pairs, (10, 12, 10, -3))
    counts = Counter()
    projection = RegionalRows({5, 7}, Catalogue, counts)
    actual = projection.pick(cat)
    assert actual == Catalogue(("a", "c", "d"), (7, 7, 5), (pairs[0], pairs[2], pairs[3]), (10, 10, -3))
    assert actual.satellites[1] is pairs[2]
    assert projection.pick(cat) is actual
    assert counts["projection_hits"] == 1
    assert counts["projected_rows_not_scanned_again"] == 1


def test_unrecognized_row_layout_is_left_to_original_consumer():
    bad = Catalogue(("a", "b"), (7,), ((1,), (2,)), (10, 12))
    counts = Counter()
    assert RegionalRows(set(), Catalogue, counts).pick(bad) is bad
    assert counts["projection_fallback"] == 1
