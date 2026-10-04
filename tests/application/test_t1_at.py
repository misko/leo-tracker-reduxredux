from types import SimpleNamespace

import pytest

from leo.application.t1_at import T1AtService
from leo.contracts.digests import canonical_digest
from tests.analysis.test_t1_at import candidates, mode, source


def capture(prepared, **changes):
    return SimpleNamespace(
        **dict(
            dict(
                capture_mode="adaptive",
                qualified=True,
                session_id=prepared.session_id,
                input_manifest_sha256=prepared.input_manifest_sha256,
                analysis_manifest_sha256=prepared.analysis_manifest_sha256,
            ),
            **changes,
        )
    )


def test_both_arms_published_with_authority_binding():
    prepared = source(candidates(20), (mode(100, list(range(20))),))
    saved = []
    service = T1AtService(
        inputs=SimpleNamespace(load=lambda session: prepared),
        products=SimpleNamespace(load=lambda digest: None, save=saved.append),
    )
    result = service.run(capture(prepared))
    assert saved == [result]
    assert result.prepared_input_sha256 == canonical_digest(prepared.model_dump(mode="json"))
    assert result.arms["fitted-c"].final.assigned == 20
    assert result.arms["zero-c"].final.assigned == 20
    assert result.identity_claimed is False


@pytest.mark.parametrize(
    "changes",
    [
        dict(capture_mode="fixed"),
        dict(qualified=False),
        dict(analysis_manifest_sha256="sha256:" + "b" * 64),
    ],
)
def test_stale_or_unqualified_input_never_published(changes):
    prepared = source((), ())
    saved = []
    service = T1AtService(
        inputs=SimpleNamespace(load=lambda session: prepared),
        products=SimpleNamespace(load=lambda digest: None, save=saved.append),
    )
    with pytest.raises(ValueError):
        service.run(capture(prepared, **changes))
    assert saved == []


def test_deadline_does_not_publish_partial_as_complete(monkeypatch):
    import leo.application.t1_at as module

    prepared = source((), ())
    saved = []

    def timeout(*a, **kw):
        raise TimeoutError()

    monkeypatch.setattr(module, "associate", timeout)
    service = T1AtService(
        inputs=SimpleNamespace(load=lambda session: prepared),
        products=SimpleNamespace(load=lambda digest: None, save=saved.append),
    )
    with pytest.raises(TimeoutError):
        service.run(capture(prepared))
    assert not saved


def test_discovery_uses_orbit_bank_instead_of_preselected_modes():
    from tests.analysis.test_t1_at_prediction import bank

    data = bank()
    saved = []
    service = T1AtService(
        inputs=SimpleNamespace(load=lambda session: data),
        products=SimpleNamespace(load=lambda digest: None, save=saved.append),
    )
    result = service.run(capture(data.manifest.evidence))
    assert saved == [result]
    assert result.prepared_input_sha256 == canonical_digest(data.manifest.model_dump(mode="json"))
    assert all(r.final.denominator == 20 for r in result.arms.values())


def test_exact_input_cache_avoids_repeating_discovery(monkeypatch):
    import leo.application.t1_at as module

    prepared = source(candidates(20), (mode(100, list(range(20))),))
    saved = []
    products = SimpleNamespace(load=lambda digest: saved[-1] if saved else None, save=saved.append)
    service = T1AtService(inputs=SimpleNamespace(load=lambda session: prepared), products=products)
    first = service.run(capture(prepared))

    def unexpected(*a, **kw):
        raise AssertionError("cached input must not be re-solved")

    monkeypatch.setattr(module, "associate", unexpected)
    assert service.run(capture(prepared)) == first
    assert len(saved) == 1


@pytest.mark.parametrize("budget", [0, -1, float("nan"), float("inf"), 1801])
def test_invalid_budget_rejected_before_loading(budget):
    prepared = source((), ())

    def unexpected(*args):
        raise AssertionError("invalid budget must fail before IO")

    service = T1AtService(
        inputs=SimpleNamespace(load=unexpected),
        products=SimpleNamespace(load=unexpected, save=unexpected),
    )
    with pytest.raises(ValueError, match="budget"):
        service.run(capture(prepared), maximum_seconds=budget)
