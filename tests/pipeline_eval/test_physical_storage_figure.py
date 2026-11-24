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
    frames = []
    for case, timing in (("DS30-0016", 4), ("DS30-0107", 1)):
        frames.append({"case": case, "qualified": True, "historical_named": cairo["clocks"][case]["stock"],
                       "measured_children": {mode: {"clock": {"exit_code": 0, "elapsed_s": timing + offset}}
                                             for mode, offset in (("ordinary", 0.2), ("frames", 0))}})
    new_rows = elapsed_rows(ordinary, cairo, packed, frames)
    assert new_rows["Standard frames · indexed read"] == [1, 4]
    with pytest.raises(ValueError, match="Both enrolled"):
        elapsed_rows(ordinary, cairo, packed, frames[:1])
    frames[0]["qualified"] = False
    with pytest.raises(ValueError, match="qualified frame"):
        elapsed_rows(ordinary, cairo, packed, frames)
    packed["positive_costs"]["stock"] = {"elapsed_s": 20}
    with pytest.raises(ValueError, match="same installed clocks"):
        elapsed_rows(ordinary, cairo, packed)
