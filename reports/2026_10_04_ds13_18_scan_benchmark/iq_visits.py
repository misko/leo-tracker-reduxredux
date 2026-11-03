"""Translate acquisition event IDs to public IQ-reader ordinal indices.

Retained IQ visits can omit acquisition events. A GLRT product's visit_index is
an event ID; read_visit_ci16 takes the ordinal in receipt.visits, not that ID.
"""


def visit_ordinals(receipt):
    result = {}
    for ordinal, visit in enumerate(receipt.visits):
        event_id = visit.event.visit_index
        if event_id in result:
            raise ValueError('duplicate retained acquisition event')
        result[event_id] = ordinal
    return result


def read_event(store, published, event_id):
    mapping = visit_ordinals(published.manifest.receipt)
    if event_id not in mapping:
        raise LookupError(f'IQ not retained for acquisition event {event_id}')
    visit, values = store.read_visit_ci16(published, mapping[event_id])
    if visit.event.visit_index != event_id:
        raise ValueError('IQ reader returned a different acquisition event')
    return visit, values
