import pytest
from batch import selected_batch


def test_batch_keeps_frozen_order_and_never_exceeds_four():
    selection = {"selected": [str(index) for index in range(16)]}
    assert selected_batch(selection, 1, 4) == ["1", "2", "3", "4"]
    assert selected_batch(selection, 13, 4) == ["13", "14", "15"]


@pytest.mark.parametrize("start,count", [(-1, 4), (16, 1), (0, 5), (0, 0)])
def test_unbounded_batches_rejected(start, count):
    with pytest.raises(ValueError):
        selected_batch({"selected": list(range(16))}, start, count)
