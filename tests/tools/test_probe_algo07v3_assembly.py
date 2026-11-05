import numpy as np
import pytest
from probe_algo07v3_assembly import AssemblyProbe, exact_result


@pytest.mark.parametrize(
    "changed",
    [
        {"x": np.array([1.00000000000001])},
        {"x": np.array([1.0], dtype=np.float32)},
        {"x": np.array([[1.0]])},
        {"y": np.array([1.0])},
    ],
)
def test_probe_rejects_value_type_shape_and_field_changes(changed):
    with pytest.raises(ValueError):
        exact_result({"x": np.array([1.0])}, changed)


def test_probe_returns_candidate_and_alternates_order():
    order = []
    expected = {"x": np.array([1.0])}
    actual = {"x": np.array([1.0])}

    def reference(*args):
        order.append("reference")
        return expected

    def candidate(*args):
        order.append("candidate")
        return actual

    probe = AssemblyProbe(reference, candidate)
    for _ in range(2):
        assert probe(np.ones(3), np.ones((3, 2))) is actual
    assert order == ["reference", "candidate", "candidate", "reference"]
    assert probe.calls == 2 and probe.shapes == {"(3, 2)": 2}
    assert not probe.failures


def test_probe_records_mismatch_and_does_not_return_a_result():
    probe = AssemblyProbe(lambda *a: dict(x=1.0), lambda *a: dict(x=2.0))
    with pytest.raises(ValueError, match="x"):
        probe(np.ones(3), np.ones((3, 2)))
    assert probe.calls == 1 and len(probe.failures) == 1
