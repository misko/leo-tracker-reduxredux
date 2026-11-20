import pytest

from tools.pipeline_eval.qualification.cold_missing import scored_arm, select_query


def _native_and_query():
    native = dict(
        observation="points", catalog={"sha256": "tle"}, catalog_timestamp_ns=10, panel="DS29"
    )
    tiles = [dict(center=[float(i), 2.0], id=f"tile-{i}") for i in (4, 1, 2, 3)]
    query = dict(native, catalog="tle", id="absent", regions=tiles)
    return native, query


def test_frozen_omitted_query_uses_first_offer_regardless_of_order_of_queries():
    native, missing = _native_and_query()
    present = dict(missing, id="present", regions=list(reversed(missing["regions"])))
    query, first = select_query(
        native, [present, missing], {"absent": "missing", "present": "present"}, "absent"
    )
    assert query == missing
    assert first == dict(center=[4.0, 2.0], id="tile-4", width_km=25.0)


def test_bad_catalogue_and_duplicate_binding_are_rejected():
    native, query = _native_and_query()
    with pytest.raises(ValueError, match="exactly"):
        select_query(native, [dict(query, catalog="different")], {"absent": "missing"}, "absent")
    with pytest.raises(ValueError, match="exactly"):
        select_query(native, [query, query], {"absent": "missing"}, "absent")


def test_omitted_counts_publications_separately_from_forced_positions():
    row = dict(
        id="DS29-0000",
        method="method",
        worker_wall_s=8.0,
        result=dict(
            status="ok",
            arms={
                "c0": dict(latlon=[1.0, 2.0], forced_latlon=[1.0, 2.0]),
                "fitted_c": dict(latlon=None, forced_latlon=[1.2, 2.0]),
            },
        ),
    )
    pos = scored_arm(row, "c0", [3.0, 2.0], omitted=True)
    assert pos["published"] and pos["false_publication"] and pos["published_error_km"] > 200
    withheld = scored_arm(row, "fitted_c", [3.0, 2.0], omitted=True)
    assert withheld["status"] == "withheld" and not withheld["false_publication"]
    assert withheld["forced_error_km"] > 190 and withheld["published_error_km"] is None
    assert not scored_arm(row, "c0", [3.0, 2.0], omitted=False)["false_publication"]
