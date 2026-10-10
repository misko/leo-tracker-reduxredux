"""Pure causal snapshot selection; no archive access or orbit propagation."""

DAY_NS = 86_400_000_000_000
MAXIMUM_DISTINCT = 10


def classify(original, alternative, selected_ids):
    """Records map NORAD to exact validated two-line tuples, or None if malformed."""
    ids = list(selected_ids)
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError("Nonempty unique original bank IDs required")
    result = {k: [] for k in ("changed", "unchanged", "missing", "malformed")}
    for number in ids:
        old = original.get(number)
        if not isinstance(old, tuple) or len(old) != 2 or not all(isinstance(x, str) for x in old):
            raise ValueError("Original selected element authority missing/malformed")
        if number not in alternative:
            result["missing"].append(number)
        else:
            new = alternative[number]
            if (
                not isinstance(new, tuple)
                or len(new) != 2
                or not all(isinstance(x, str) for x in new)
            ):
                result["malformed"].append(number)
            else:
                result["unchanged" if new == old else "changed"].append(number)
    return result


def select_earlier_changed(original_ref, original_records, selected_ids, snapshots, records):
    """First changed shared catalogue, newest first, same provider, fixed caps.

    Name-only changes are excluded by using validated element-line pairs only.
    Missing/malformed objects never qualify as changed common objects. One
    shared snapshot is chosen for both arms and every selected satellite.
    """
    candidates = [
        s
        for s in snapshots
        if s["provider"] == original_ref["provider"]
        and original_ref["collected_utc_ns"] - DAY_NS
        <= s["collected_utc_ns"]
        < original_ref["collected_utc_ns"]
    ]
    candidates.sort(key=lambda s: (s["collected_utc_ns"], s["sha256"]), reverse=True)
    seen = {original_ref["sha256"]}
    inspected = []
    for snapshot in candidates:
        if snapshot["sha256"] in seen:
            continue
        if len(inspected) >= MAXIMUM_DISTINCT:
            break
        seen.add(snapshot["sha256"])
        # Payloads are supplied by a future digest-verifying public reader.
        if snapshot["sha256"] not in records:
            inspected.append(dict(snapshot=snapshot, status="payload-unavailable"))
            continue
        categories = classify(original_records, records[snapshot["sha256"]], selected_ids)
        inspected.append(dict(snapshot=snapshot, status="classified", candidates=categories))
        if categories["changed"]:
            return dict(selected=snapshot, inspected=inspected, reason="first-changed-common-ID")
    return dict(
        selected=None, inspected=inspected, reason="no-changed-common-ID-within-fixed-bound"
    )
