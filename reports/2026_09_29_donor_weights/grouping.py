"""Structural donor groups disjoint from all target recordings."""


def groups(records, excluded):
    result = []
    current = []
    dataset = None
    for r in records:
        if r["dataset"] != dataset or r["session_id"] in excluded:
            if current:
                result.append(current)
                current = []
            dataset = r["dataset"]
        if r["session_id"] in excluded:
            continue
        current.append(r)
        if len(current) == 8:
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result


def available(group, target_start):
    return group["available_utc_ns"] < target_start
