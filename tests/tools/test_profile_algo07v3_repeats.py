import numpy as np
from profile_algo07v3_repeats import RepeatProbe


def test_probe_computes_every_call_and_measures_bounded_reuse():
    calls = []

    def operation(raw, *, scale=1.0):
        calls.append(raw.copy())
        return {"value": raw * scale}

    times = iter(range(100))
    probe = RepeatProbe(operation, capacities=(1, 2), clock=lambda: next(times))
    a, b = np.array([1.0]), np.array([2.0])
    first = probe(a)
    first["value"][:] = 99
    np.testing.assert_array_equal(probe(a.copy(), scale=1.0)["value"], a)
    probe(b)
    probe(a)
    assert len(calls) == 4
    report = probe.report()
    assert report["calls"] == 4 and report["unique_input_digests"] == 2
    assert report["numerical_calls_skipped"] == 0
    assert report["lru_capacities"][1] == {"hits": 1, "repeated_compute_seconds": 1.0}
    assert report["lru_capacities"][2] == {"hits": 2, "repeated_compute_seconds": 2.0}


def test_input_key_includes_content_shape_type_and_policy():
    def operation(raw, *, iterations=256):
        return raw

    probe = RepeatProbe(operation)
    a = np.arange(4, dtype=float).reshape(2, 2)
    original = probe.key((a,), {})
    assert original == probe.key((a.copy(order="F"),), {"iterations": 256})
    assert original != probe.key((a.ravel(),), {})
    assert original != probe.key((a.astype(np.int64),), {})
    assert original != probe.key((a,), {"iterations": 255})
    a[0, 0] = 9
    assert original != probe.key((a,), {})
