import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import stress  # noqa: E402
from tracking import Key  # noqa: E402


def test_wrong_cache_restores_destination_and_never_changes_source():
    key = Key('s', 0, 1, 'lower', 2500000)
    source = Key('s', 0, 4, 'lower', 2500000)
    a, b = object(), object()
    tracker = SimpleNamespace(states={key: a, source: b})
    recipe = {'wrong_cache': {'block_offset_ranges_end_exclusive': [[40, 48]],
                              'channel_remap': {'1': 4}}}
    with stress.cache_lookup(tracker, key, 40, 'wrong_cache', recipe) as injected:
        assert injected and tracker.states[key] is b
    assert tracker.states == {key: a, source: b}
    with stress.cache_lookup(tracker, key, 48, 'wrong_cache', recipe) as injected:
        assert not injected and tracker.states[key] is a


def test_outage_end_is_exclusive_and_drop_preserves_other_sessions():
    key = Key('s', 0, 1, 'lower', 2500000)
    other = Key('t', 0, 1, 'lower', 2500000)
    tracker = SimpleNamespace(states={key: 1, other: 2})
    case = {'block_offset': 24, 'session_id': 's'}
    recipe = {'processing_outage': {'block_offset_ranges_end_exclusive': [[24, 28]]},
              'forced_state_drop': {'before_block_offsets': [16]}}
    assert stress.prepare_visit(tracker, case, 'processing_outage', recipe)
    assert tracker.states[key] == 1
    assert not stress.prepare_visit(tracker, dict(case, block_offset=28),
                                    'processing_outage', recipe)
    stress.prepare_visit(tracker, dict(case, block_offset=16), 'forced_state_drop', recipe)
    assert tracker.states == {other: 2}
