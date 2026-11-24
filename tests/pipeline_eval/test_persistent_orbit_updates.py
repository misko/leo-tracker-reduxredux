from hashlib import sha256
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/persistent_orbit_updates.py"
SPEC = importlib.util.spec_from_file_location("persistent_orbit_updates", SCRIPT)
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


@pytest.fixture
def released(tmp_path, monkeypatch):
    source = tmp_path / "fake_phase_prior.py"
    source.write_text("def transition(a, b, c):\n    calls.append((a, b, c))\n"
                      "    return {'epoch': c['epoch']} if c['epoch'] else None\n")
    prior = ModuleType("fake_phase_prior")
    prior.__file__, prior.calls = str(source), []
    exec(compile(source.read_text(), str(source), "exec"), prior.__dict__)
    monkeypatch.setattr(study, "SOURCE_SHA256", sha256(source.read_bytes()).hexdigest())
    return prior, source


def records(stamp=8, epoch=3, suffix=""):
    return [dict(lines=[str(index), suffix], epoch=value, collected_utc_ns=stamp)
            for index, value in enumerate((1, 2, epoch))]


def test_chronological_hits_return_independent_copies(released):
    prior, source = released
    original = prior.transition
    cache = study.OrbitUpdates()
    with cache.request(prior, source, 10) as first:
        prior.transition(*records())["epoch"] = 99
        assert prior.transition(*records(epoch=0)) is None
    assert prior.transition is original
    assert first == {"misses": 2}
    with cache.request(prior, source, 11) as second:
        assert prior.transition(*records()) == {"epoch": 3}
        assert prior.transition(*records(epoch=0)) is None
        assert prior.transition(*records(stamp=9)) == {"epoch": 3}
        assert prior.transition(*records(suffix="1")) == {"epoch": 3}
    assert second == {"hits": 2, "misses": 2}
    assert len(prior.calls) == 4


def test_cutoff_eviction_chronology_and_guard_fallback(released):
    prior, source = released
    cache = study.OrbitUpdates(capacity=1)
    with cache.request(prior, source, 10) as first:
        prior.transition(*records())
        prior.transition(*records(stamp=10))
        prior.transition(*records(stamp=11))
        prior.transition(*records(epoch=11))
    assert first == {"misses": 2, "evicted": 1, "original_unsupported": 2}
    with cache.request(prior, source, 10) as reset:
        prior.transition(*records(stamp=10))
    assert reset == {"misses": 1, "chronology_resets": 1}
    original = prior.transition
    source.write_text("# different runtime source\n")
    with cache.request(prior, source, 11) as rejected:
        assert prior.transition is original
    assert rejected == {"incompatible_source": 1}
    assert not cache.results and cache.cutoff is None
