"""Map persisted event IDs to public reader ordinals, with exact metadata guards."""


def visit_ordinals(visits, metadata):
    by_id = {}
    for ordinal, visit in enumerate(visits):
        event_id = visit.event.visit_index
        if event_id in by_id:
            raise ValueError("duplicate persisted event ID")
        by_id[event_id] = ordinal
    selected = {}
    for event_string, expected in metadata["visits"].items():
        event_id = int(event_string)
        if event_id not in by_id:
            raise ValueError(f"original event {event_id} absent from manifest")
        ordinal = by_id[event_id]
        visit = visits[ordinal]
        if (
            visit.event.valid_start_counter != expected["valid_start_counter"]
            or visit.valid_sample_count != expected["sample_count"]
        ):
            raise ValueError("event counter/count identity mismatch")
        selected[event_id] = ordinal
    for window in metadata["windows"]:
        visit = visits[selected[window["visit"]]]
        if (
            visit.event.target.channel != window["channel"]
            or visit.event.target.edge.value != window["edge"]
        ):
            raise ValueError("event RF channel/edge identity mismatch")
    return selected
