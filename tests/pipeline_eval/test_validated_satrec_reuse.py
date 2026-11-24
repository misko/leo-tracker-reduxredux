from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.validated_satrec_reuse import ORIGINAL_SOURCE, RETENTION_SOURCE, ScanElements, private_source


def test_private_loader_reproduces_exact_measured_source_and_keeps_original_eligible():
    path = Path(__file__).resolve().parents[2]/"reports/ALGO08/v3/historical_orbit_index.py"
    source = path.read_bytes()
    assert sha256(source).hexdigest() == ORIGINAL_SOURCE
    assert sha256(private_source(source)).hexdigest() == RETENTION_SOURCE
    with pytest.raises(ValueError, match="frozen original"):
        private_source(source+b"\n")


def test_exact_line_pair_reuses_a_real_constructor_result_and_evicts_oldest():
    requests = []

    def construct(first, second):
        value = object()
        requests.append((first, second, value))
        return value

    reuse = ScanElements(construct, limit=2)
    old = reuse.after_parse("original first", "original second")
    retained = reuse.after_parse("same catalogue number", "changed epoch")
    reuse.after_parse("same catalogue number", "another epoch")
    assert len(reuse.pending) == 2 and reuse.counts["evicted"] == 1
    assert reuse.elected("same catalogue number", "changed epoch") is retained
    assert reuse.elected("original first", "original second") is not old
    assert reuse.counts["reused_elected"] == 1 and reuse.counts["elected_constructions"] == 1
    assert len(requests) == 4


def test_retention_is_cleared_if_the_original_export_check_declines_the_request(monkeypatch):
    @contextmanager
    def installed(materialize):
        assert callable(materialize)
        yield {"native_outputs": 0}

    monkeypatch.setitem(sys.modules, "historical_orbit_index", SimpleNamespace(elected_elements=installed))
    reuse = ScanElements(lambda first, second: (first, second), limit=2)
    with pytest.raises(ValueError, match="uncertified export"):
        with reuse.scope():
            reuse.after_parse("line1", "line2")
            raise ValueError("uncertified export")
    assert reuse.pending == {} and reuse.counts["released_unused"] == 1
