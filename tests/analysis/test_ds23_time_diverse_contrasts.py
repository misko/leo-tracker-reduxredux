from inventory_ds23_time_diverse_contrasts import triplet


def row(t,probe=None,margin=.3):
    return dict(time_s=t,probe=t if probe is None else probe,minimum_native_margin=margin)


def test_repeated_nearby_measurements_do_not_count_as_long_baseline():
    assert triplet([row(0),row(.1),row(.3)]) is None
    assert triplet([row(0),row(1),row(30)]) is None


def test_endpoints_and_independent_middle_probe_are_retained():
    rows=[row(0),row(5),row(14),row(29),row(30)]
    assert [r['time_s'] for r in triplet(rows)]==[0,14,30]
    assert triplet([row(0,probe=1),row(15,probe=1),row(30,probe=2)]) is None
