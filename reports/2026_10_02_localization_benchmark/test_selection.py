import pytest
from selection import MODEL_NAMES, select


def test_selection_is_order_independent_and_without_replacement():
    population = [{"session_id": f"scan-{index:03}"} for index in range(87)]
    selected = select(population)
    assert selected == select(list(reversed(population)))
    assert len(selected) == len(set(selected)) == 16
    assert set(selected) <= {row["session_id"] for row in population}
    assert len(MODEL_NAMES) == len(set(MODEL_NAMES)) == 13


def test_duplicate_capture_population_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        select([{"session_id": "same"}] * 20)
