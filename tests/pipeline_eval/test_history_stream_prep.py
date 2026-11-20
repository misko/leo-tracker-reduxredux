from collections import OrderedDict
from types import SimpleNamespace

import pytest

from leo import application
from tools.pipeline_eval.variants.history_stream_prep import history_cache, last_use


class Parser:
    def __init__(self):
        self.maximum_bytes, self.bytes = 200, 0
        self.hits, self.misses = 0, 0
        self._records = OrderedDict()

    def __call__(self, text):
        if text == "broken":
            raise ValueError("invalid TLE")
        if text in self._records:
            self.hits += 1
        else:
            self.misses += 1
            if len(text) <= self.maximum_bytes:
                self._records[text] = ((text,), len(text))
                self.bytes += len(text)
        return tuple(text)

    def statistics(self):
        return dict(hits=self.hits, misses=self.misses, retained_bytes=self.bytes)


def test_last_use_drains_reused_rows_and_does_not_cache_final_misses():
    parser = Parser()
    previous = parser("abc")
    parser("xyz")
    receipt = {}
    with last_use(parser, receipt) as consume:
        assert consume("abc") == previous
        assert parser.bytes == 3
        assert consume("long-snapshot") == tuple("long-snapshot")
        assert list(parser._records) == ["xyz"]
        assert parser.maximum_bytes == 0
    assert parser.maximum_bytes == 200
    assert receipt == dict(
        starting_entries=2,
        starting_bytes=6,
        released_bytes=3,
        released_entries=1,
        remaining_entries=1,
        remaining_bytes=3,
        last_use_hits=1,
        last_use_misses=1,
    )


def test_failed_parse_preserves_error_and_restores_original_budget():
    parser = Parser()
    parser("untouched")
    with pytest.raises(ValueError, match="invalid TLE"), last_use(parser, {}) as consume:
        consume("broken")
    assert list(parser._records) == ["untouched"]
    assert parser.maximum_bytes == 200


def test_final_use_only_drains_the_preparation_owned_instance(monkeypatch):
    def prepare(*, element_parser):
        return [element_parser(text) for text in ("abc", "new")]

    module = SimpleNamespace(ElementParser=Parser, prepare_phase_history=prepare)
    monkeypatch.setattr(application, "localization_v3", module, raising=False)
    outside = Parser()
    outside("abc")
    with history_cache() as receipts:
        owned = module.ElementParser()
        owned("abc")
        assert module.prepare_phase_history(element_parser=owned) == module.prepare_phase_history(
            element_parser=outside
        )
        assert list(outside._records) == ["abc", "new"]
        assert list(owned._records) == []
        assert len(receipts) == 1 and receipts[0]["released_entries"] == 1
    assert module.ElementParser is Parser and module.prepare_phase_history is prepare
