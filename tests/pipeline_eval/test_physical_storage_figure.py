import pytest

from reports.ALGO08.v3.physical_storage_figure import elapsed_rows


def test_packed_first_use_is_charged_on_each_recording():
    ordinary = {"cases": {}}
    cairo = {"qualified": True, "clocks": {}}
    packed = {"qualified": True}
    for i, (case, source) in enumerate((("DS30-0107", "costs"), ("DS30-0016", "positive_costs")), 1):
        stock = {"elapsed_s": i * 5}
        candidate = {"elapsed_s": i * 3}
        ordinary["cases"][case] = {"stock": {"clock": stock}, "candidate": {"clock": candidate}}
        cairo["clocks"][case] = {"stock": stock, "candidate": candidate}
        packed[source] = {"stock": stock, "scopes": {"ready": [i, i], "first": [i + 4, i + 4]}}
    rows = elapsed_rows(ordinary, cairo, packed)
    assert rows["Split archive ready"] == [1, 2]
    assert rows["Split archive first use"] == [5, 6]
    packed["positive_costs"]["stock"] = {"elapsed_s": 20}
    with pytest.raises(ValueError, match="same installed clocks"):
        elapsed_rows(ordinary, cairo, packed)
