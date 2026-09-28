import pytest

from tools import ds7_wave2_search_adapter as adapter


def test_model_hooks_restore_after_failure(monkeypatch):
    old_model = adapter.search.baseline
    old_profile = adapter.fast.baseline.profile

    def fail(request):
        assert adapter.search.baseline is adapter.fast.baseline
        assert adapter.fast.baseline.profile is adapter.fast.profile
        raise ValueError("synthetic transport failure")

    monkeypatch.setattr(adapter.search, "estimate", fail)
    with pytest.raises(ValueError, match="synthetic transport"):
        adapter.estimate({})
    assert adapter.search.baseline is old_model
    assert adapter.fast.baseline.profile is old_profile
