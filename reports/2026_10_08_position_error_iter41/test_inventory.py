import copy

from region_inventory import inventory


def test_reference_fields_do_not_affect_inventory():
    doc = {
        "methods": [
            {"points": [dict(spacing_km=40, objective=i, east_km=i, north_km=0) for i in range(40)]}
        ],
        "diagnostics": {
            "retained_basins": [dict(east_km=1, north_km=0), dict(east_km=100, north_km=100)]
        },
    }
    changed = copy.deepcopy(doc)
    changed.update(reference_latitude_deg=-80, reference_longitude_deg=123)
    assert inventory(doc) == inventory(changed)
    assert len(inventory(doc)) == 33
    assert inventory(doc)[-1]["point"] == [100, 100]


def test_ties_use_coordinates_and_fine_cells_are_excluded():
    doc = {
        "methods": [
            {
                "points": [
                    dict(spacing_km=s, objective=o, east_km=e, north_km=0)
                    for s, o, e in [(40, 1, 2), (5, 0, 0), (40, 1, 1)]
                ]
            }
        ],
        "diagnostics": {"retained_basins": []},
    }
    assert [r["point"] for r in inventory(doc)] == [[1, 0], [2, 0]]
