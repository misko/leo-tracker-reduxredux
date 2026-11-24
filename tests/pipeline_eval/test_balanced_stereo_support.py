from reports.ALGO08.v3.balanced_stereo_support import predecessor_support


def test_half_duty_at_two_second_cadence_cannot_supply_three_recent_donors():
    events = []
    for index in range(24):
        cycle, slot = divmod(index, 8)
        paid = slot == 0 or (cycle+slot) % 2 == 0
        events.append(dict(stream=("lower", 1, 100.), sample=index*20_000_000, paid=paid,
                           states=["measured_positive", "measured_empty"] if paid else ["unmeasured"]*2))
    result = predecessor_support(events)
    assert result["can_have_three_measured_predecessors"] == 0
    assert sum(result["paid_visit_histogram"].values()) == sum(row["paid"] for row in events)
    assert result["paid_visit_histogram"] == result["measured_positive_by_receiver"][0]
    assert not result["measured_positive_by_receiver"][1]
