"""Outcome-independent cache perturbations from the frozen dataset recipe."""
from contextlib import contextmanager
from dataclasses import replace


def in_ranges(offset, ranges):
    return any(left <= offset < right for left, right in ranges)


def prepare_visit(tracker, case, variant, recipe):
    offset = case['block_offset']
    if variant == 'forced_state_drop' and offset in recipe[variant]['before_block_offsets']:
        tracker.states = {key: state for key, state in tracker.states.items()
                          if key.session != case['session_id']}
    return (variant == 'processing_outage' and
            in_ranges(offset, recipe[variant]['block_offset_ranges_end_exclusive']))


@contextmanager
def cache_lookup(tracker, key, offset, variant, recipe):
    """Poison only the lookup; update remains attached to the observed channel."""
    if (variant != 'wrong_cache' or not
            in_ranges(offset, recipe[variant]['block_offset_ranges_end_exclusive'])):
        yield False
        return
    saved = tracker.states.pop(key, None)
    remapped = replace(key, channel=recipe[variant]['channel_remap'][str(key.channel)])
    other = tracker.states.get(remapped)
    if other is not None:
        tracker.states[key] = other
    try:
        yield True
    finally:
        tracker.states.pop(key, None)
        if saved is not None:
            tracker.states[key] = saved
