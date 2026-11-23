from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_dispatch_requires_the_installed_retry_handler(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    relay = import_module("cumulative_history_dispatch")
    ordinary = object()

    def previous(scan, labels):
        raise AssertionError

    def history_support():
        return ordinary

    requests = []
    scan, labels = object(), (0, 1)
    modes = SimpleNamespace(previous_bank=previous)
    position = SimpleNamespace(history_support=history_support)

    def confirm(error, source, line, received, selected, orbit_modes, subset):
        assert isinstance(error, AssertionError) and source is previous and received is scan and selected is labels
        assert orbit_modes is modes
        requests.append(line)
        return object(), dict(failed_previous_norads=[42])

    monkeypatch.setattr(relay, "recovered_catalogue", confirm)
    line = previous.__code__.co_firstlineno + 1
    with relay.at_installed_retry(position, modes, None, line=line):
        with pytest.raises(AssertionError):
            previous(scan, labels)
        assert not requests and position.history_support() is ordinary
        try:
            raise AssertionError("unrelated caller")
        except AssertionError:
            assert position.history_support() is ordinary
        with pytest.raises(relay.NamedRecoveryRequired) as caught:
            try:
                previous(scan, labels)
            except AssertionError:
                position.history_support()
    assert caught.value.event["failed_previous_norads"] == [42]
    assert requests == [line]
    assert position.history_support is history_support
