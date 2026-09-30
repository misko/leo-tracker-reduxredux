from sysinfo_consumer import run


def test_consumer_conversion_and_nonexclusive_change_gate():
    result = run()
    assert len(result["conversions"]) == 24
    assert len(result["gates"]) == 57
    assert sum(r["changed"] for r in result["gates"]) == 56
