from collections import namedtuple

from reports.ALGO08.v3.regional_history_rows import HistoryRows


Catalogue = namedtuple("Catalogue", "names satellite_numbers satellites epochs")


def test_history_selection_follows_current_region_and_preserves_source_order_and_duplicates():
    counts = dict(history_input_rows=0, history_retained_rows=0)
    view = HistoryRows(Catalogue, counts)
    cat = Catalogue(("a", "b", "c"), (42, 7, 42), (1, 2, 3), (19, 20, 18))
    assert view.filter(cat) is cat
    view.select(frozenset({42}))
    assert view.filter(cat) == Catalogue(("a", "c"), (42, 42), (1, 3), (19, 18))
    changed = cat._replace(satellites=(5, 4, 3))
    assert view.filter(changed).satellites == (5, 3)
    view.select(frozenset({7}))
    assert view.filter(cat).names == ("b",)
    view.select(frozenset())
    assert not view.filter(cat).names
    assert counts == dict(history_input_rows=12, history_retained_rows=5)
    assert view.filter("fallback parser") == "fallback parser"
