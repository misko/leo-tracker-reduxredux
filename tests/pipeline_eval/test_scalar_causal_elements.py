"""Preserve the causal parser's scalar orbit records and memory fallback."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sgp4.exporter import export_tle

from leo.sky import propagation
from tests.operations.test_causal_tle_catalogue import at_day
from tools.pipeline_eval.variants import algo08_causal_reuse as runtime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
import scalar_causal_elements as advance


def installed_shape(constructor=runtime.Satrec.twoline2rv):
    return advance.materializer(constructor, runtime.ElementSetError,
                                propagation._UNIX_EPOCH_JULIAN_DAY, propagation._NS_PER_DAY)


@pytest.mark.parametrize("budget", [256 * 1024**2, 100])
def test_materialization_matches_original_catalogue_cache_and_budget(budget):
    a = at_day(13.1020304)
    b = at_day(13.1020305)
    newest_name = b.replace("STARLINK-1008", "STARLINK EXACT RENAME")
    workload = (a + b, newest_name, a, a + b)

    def evaluate():
        parser = runtime.CausalPreparationParser(budget)
        rows = []
        for text in workload:
            catalogue = parser(text)
            rows.append((catalogue.names, catalogue.satellite_numbers, catalogue.element_epoch_utc_ns(),
                         tuple(export_tle(satellite) for satellite in catalogue.satellites)))
        return rows, parser.stats, parser.retained_bytes, len(parser.elements), len(parser.catalogues)

    reference = evaluate()
    with patch.object(runtime.CausalPreparationParser, "_element", installed_shape()):
        assert evaluate() == reference
    if runtime.accelerated and budget > 100:
        assert reference[1]["element_hits"] > 0 and reference[1]["snapshot_hits"] > 0
    else:
        assert reference[1]["fallback_calls"]


def test_materialization_retains_the_original_orbit_error_contract():
    def reject(*lines):
        raise RuntimeError("invalid element")

    parser = runtime.CausalPreparationParser()
    record = SimpleNamespace(first_line="one", second_line="two", satellite_number=789)
    with pytest.raises(runtime.ElementSetError, match="catalog object 789") as caught:
        installed_shape(reject)(parser, record)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert parser.stats["element_misses"] == 1 and not parser.elements


def test_unreviewed_installed_sources_keep_original_parser(monkeypatch):
    monkeypatch.setattr(advance, "eligible", lambda *args: False)
    original = runtime.CausalPreparationParser._element
    audit = {}
    with advance.scalar_causal_elements(audit):
        assert runtime.CausalPreparationParser._element is original
    assert audit == {"source_guard": False}
