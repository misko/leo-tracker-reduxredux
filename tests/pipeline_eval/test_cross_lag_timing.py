from reports.ALGO08.v3.cross_lag_timing import frontier, triggered


def test_rule_expands_before_carrier_on_low_contrast_or_disagreement():
    rule = (4, 1.1)
    assert not triggered({"contrast": 1.1, "distance": 4}, rule)
    assert triggered({"contrast": 1.09, "distance": 0}, rule)
    assert triggered({"contrast": 1.2, "distance": 5}, rule)
    assert triggered({"contrast": None, "distance": 0}, rule)
    assert triggered({"contrast": 1.2, "distance": 0}, (1666, None))


def test_frontier_charges_false_expansion_and_requires_ordered_signed_parity():
    def row(before, later, contrast):
        return {"result": {"ordinary": {"blob": before}, "cue": {"blob": later, "cpu_ns": 100,
                                                               "cue": {"distance": 0, "contrast": contrast}},
                           "expanded": {"blob": before, "cpu_ns": 200}}}

    chosen, _ = frontier([row("a", "", 1.09), row("b", "b", 1.2), row("", "", 1.07)])
    assert chosen["rule"] == [1666, 1.1]
    assert chosen["wrong"] == chosen["rescued"] == chosen["false_expansion"] == 1
    assert chosen["cpu_ns"] == 500
