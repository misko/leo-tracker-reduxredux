import pytest

from leo.analysis.research.position_shape_subsets import shape_preserving_order
from leo.analysis.research.position_subsets import Observation


def test_packets_preserve_span_and_never_use_heldout():
    rows = tuple(
        Observation(f"{t}:{i}", str(t), str(t), (100 * t + i) * 10**9, i != 4, "ch1", 10_000_000)
        for t in range(12)
        for i in range(9)
    )
    result = shape_preserving_order(rows, seed=3, packet_size=3)
    assert result == shape_preserving_order(tuple(reversed(rows)), seed=3, packet_size=3)
    assert len(set(result)) == len(result) == 96
    assert set(result) == {r.observation_id for r in rows if r.fitting}
    for i in range(0, 36, 3):
        packet = result[i : i + 3]
        assert len({p.split(":")[0] for p in packet}) == 1
        assert packet[0].endswith(":0") and packet[1].endswith(":8")
        assert packet[2].endswith((":3", ":5"))
    for f in (1 / 32, 1 / 16, 1 / 8):
        assert len(result[: int(96 * f)]) == int(96 * f)


def test_empty_and_bad_inputs():
    assert shape_preserving_order((), seed=0) == ()
    with pytest.raises(ValueError):
        shape_preserving_order((), seed=0, packet_size=1)
    row = Observation("a", "a", "a", 0, True, "ch1", 1)
    with pytest.raises(ValueError, match="duplicate"):
        shape_preserving_order((row, row), seed=0)
