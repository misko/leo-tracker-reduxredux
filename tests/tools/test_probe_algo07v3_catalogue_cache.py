import pytest
from probe_algo07v3_catalogue_cache import ObservedParser, inputs, recovery


def test_recovery_injection_preserves_catalogue_policy_and_observes_parser(monkeypatch):
    seen = []
    parser = ObservedParser(lambda text: seen.append(text))

    def catalogue(reader, cutoff, **kwargs):
        assert reader == 'archive' and cutoff == 123
        assert kwargs['maximum_age_s'] == 72 * 3600
        kwargs['element_parser']('original snapshot')
        raise ValueError('sentinel')

    monkeypatch.setattr(inputs, 'causal_catalogue', catalogue)
    with pytest.raises(ValueError, match='sentinel'):
        recovery(parser)('archive', 123)
    assert seen == ['original snapshot'] and parser.calls == 1 and parser.seconds >= 0


def test_observer_preserves_parser_errors_and_counts_attempts():
    def failing(text):
        raise ValueError('malformed TLE')

    parser = ObservedParser(failing)
    with pytest.raises(ValueError, match='malformed TLE'):
        parser('bad')
    assert parser.calls == 1 and parser.seconds >= 0
