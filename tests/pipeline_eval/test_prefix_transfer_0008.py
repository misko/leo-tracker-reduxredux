from reports.ALGO08.v3.prefix_transfer_0008_score import measured_delta


def test_owner_change_respects_prefix_and_suffix_and_distinguishes_role_changes():
    before = {"a": [10, "conditional"], "b": [11, "predictive"],
              "c": [12, "predictive"], "d": [13, "conditional"]}
    after = {"a": [15, "conditional"], "b": [11, "conditional"],
             "d": [13, "conditional"], "e": [16, "predictive"]}
    prefix = measured_delta(before, after, {"a", "c", "e"})
    suffix = measured_delta(before, after, {"b", "d"})
    assert prefix == dict(before=2, after=2, shared=1, added=1, removed=1,
                          changed_norad=1, changed_role=0, changed_ids=["a","c","e"])
    assert suffix == dict(before=2, after=2, shared=2, added=0, removed=0,
                          changed_norad=0, changed_role=1, changed_ids=["b"])
