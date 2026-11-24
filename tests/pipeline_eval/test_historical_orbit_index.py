"""Check immutable input authority and exact ordering before materialization."""

from dataclasses import dataclass
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from historical_orbit_index import HOUR_NS, SourceIndex, VerifiedIndexReader, phase_history


@dataclass(order=True)
class Snapshot:
    collected_utc_ns: int
    sha256: str
    byte_size: int = 100


def test_content_hit_requires_successfully_verified_supplied_bytes():
    live = Snapshot(1, "digest")
    requested = []

    def verified(snapshot):
        requested.append(snapshot)
        if snapshot is not live:
            raise ValueError("body invalidated")
        return "authorized record"

    class Index:
        bodies = {"digest": "prior index entry"}

        def catalogue(self, digest, content):
            return self.bodies[digest], content

    reader = VerifiedIndexReader(SimpleNamespace(read=verified), Index())
    with pytest.raises(ValueError, match="just-verified"):
        reader.parse("authorized record")
    assert reader.parse(reader.read(live)) == ("prior index entry", "authorized record")
    with pytest.raises(ValueError, match="body invalidated"):
        reader.read(Snapshot(2, "digest"))
    assert len(requested) == 2 and reader.hits == reader.reads == 1


def test_source_pairs_reuse_authoritative_number_and_epoch_only(monkeypatch):
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed

    calls = []
    satellite = SimpleNamespace(satnum=25544, jdsatepoch=2440588.5, jdsatepochF=.5)

    def make(*lines):
        calls.append(lines)
        return satellite

    monkeypatch.setattr(installed, "Satrec", SimpleNamespace(twoline2rv=make))
    monkeypatch.setattr(installed, "parse_element_set_records", lambda name: [
        SimpleNamespace(first_line="first", second_line="second", name=name)])
    index = SourceIndex()
    a = index.catalogue("A", "first name")
    b = index.catalogue("B", "later name")
    assert a.names == ("first name",) and b.names == ("later name",)
    assert a.satellites == b.satellites == (("first", "second"),)
    assert a.satellite_numbers == b.satellite_numbers == (25544,)
    assert a.epochs == b.epochs == (36*HOUR_NS,)
    assert calls == [("first", "second")]


def test_phase_exports_only_original_winners_preserving_causal_ties():
    from leo.operations.localization_v3_inputs import distinct_epochs
    from tools.pipeline_eval.variants.algo08_causal_reuse import PreparedCatalogue

    cutoff = 100*HOUR_NS
    epochs = [cutoff-8_000_000_000, cutoff-800_000_000, cutoff-300_000_000, cutoff+1]
    catalogue = {
        "early": PreparedCatalogue(("a", "b", "c"), (1, 1, 7), (("old",), ("near",), ("outside",)),
                                   (epochs[0], epochs[1], epochs[0])),
        "later": PreparedCatalogue(("a", "b", "c"), (1, 1, 1), (("losing_tie",), ("latest",), ("future",)),
                                   (epochs[0], epochs[2], epochs[3])),
    }
    snapshots = [Snapshot(cutoff-10, "early"), Snapshot(cutoff-9, "early"), Snapshot(cutoff-8, "later"),
                 Snapshot(cutoff+1, "future_body")]
    reader = SimpleNamespace(list_snapshots=lambda _: snapshots, read=lambda snapshot: snapshot.sha256)
    exported = []

    def emit(pair):
        exported.append(pair)
        return pair

    result = phase_history(reader, {"1": {}}, dict(causal_cutoff_utc_ns=cutoff, anchor_utc_ns=cutoff-100),
                           element_parser=catalogue.get, export=emit, distinct=distinct_epochs)
    assert exported == [("old",), ("latest",)]
    assert [row["snapshot_sha256"] for row in result["past_versions"]["1"]] == ["early", "later"]
    assert result["sources"][0] == dict(collected_utc_ns=cutoff-10, sha256="early")
