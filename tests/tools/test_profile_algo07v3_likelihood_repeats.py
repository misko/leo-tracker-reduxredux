import numpy as np
import pytest
from profile_algo07v3_likelihood_repeats import MODULES, Observer, input_signature, observe


def arguments():
    return (np.arange(4.), np.ones((4, 2)), np.ones(4), np.zeros(4, dtype=int))


def test_observer_executes_repeats_and_binds_defaults_and_priors():
    observer, executed = Observer(), []

    def original(*args, **kwargs):
        executed.append(1)
        return dict(value=np.array([-0., 2.]))

    observer.call(original, 'a', arguments(), {})
    observer.call(original, 'a', arguments(), {'iterations': 256})
    observer.call(original, 'b', arguments(), {})
    observer.call(original, 'b', arguments(), {'noise_nu': 5.})
    assert len(executed) == 4 and len(observer.seen) == 2
    assert observer.rows['a']['repeat_calls'] == 1
    assert observer.rows['b']['cross_label_calls'] == 1


def test_keys_distinguish_layout_signed_zero_and_contents():
    a = np.arange(12.).reshape(3, 4)
    variants = [a, np.asfortranarray(a), a + 1, a.copy()]
    variants[-1][0, 0] = -0.
    assert len({input_signature({'a': value}) for value in variants}) == 4


def test_inconsistent_return_is_rejected():
    observer = Observer()
    observer.call(lambda *a: 1, 'a', arguments(), {})
    with pytest.raises(ValueError, match='changed its result'):
        observer.call(lambda *a: 2, 'a', arguments(), {})


def test_child_reset_and_hook_restoration(monkeypatch):
    observer = Observer()
    observer.call(lambda *a: 1, 'a', arguments(), {})
    monkeypatch.setattr('profile_algo07v3_likelihood_repeats.os.getpid', lambda: -42)
    observer.call(lambda *a: 1, 'a', arguments(), {})
    assert observer.pid == -42 and observer.rows['a']['calls'] == 1
    originals = [m.hierarchical_bound for m in MODULES]
    with pytest.raises(RuntimeError), observe(observer, lambda: 'test'):
        assert all(m.hierarchical_bound is not f for m, f in zip(MODULES, originals, strict=True))
        raise RuntimeError('fail')
    assert [m.hierarchical_bound for m in MODULES] == originals
