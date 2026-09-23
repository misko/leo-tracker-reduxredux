from tools.research.bind_longarc_phase_sources import fresh_whole_visit_partition


def test_fresh_partition_is_seeded_disjoint_and_whole_visit():
    observations = [
        {"visit_index": visit, "time_s": float(visit) / 10}
        for visit in range(78)
    ]
    first = fresh_whole_visit_partition(observations)
    second = fresh_whole_visit_partition(list(reversed(observations)))

    assert first == second
    assert len(first["training_visit_indices"]) == 42
    assert len(first["held_visit_indices"]) == 36
    assert not set(first["training_visit_indices"]) & set(first["held_visit_indices"])
    assert {row["visit_index"] for row in first["rows"]} == set(range(78))
    for stratum in range(6):
        rows = [row for row in first["rows"] if row["temporal_stratum"] == stratum]
        assert len(rows) == 13
        assert {row["partition"] for row in rows} == {"train", "held"}
