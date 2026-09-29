"""Validated catalogue-row mapping and recording-level recurrence."""


def map_rows(numbers, rows, expected_size):
    if len(numbers) != expected_size or len(set(numbers)) != len(numbers):
        raise ValueError("Catalogue size or identity uniqueness mismatch")
    if any(type(i) is not int or not 0 <= i < expected_size for i in rows):
        raise ValueError("Invalid catalogue row")
    if len(set(rows)) != len(rows):
        raise ValueError("Duplicate candidate row")
    return [numbers[i] for i in rows]


def support_counts(target, donor_index, scans, outside_block=False):
    allowed = {
        sid
        for sid, s in scans.items()
        if s["start_utc_ns"] < target["start_utc_ns"]
        and (not outside_block or s["block"] != target["block"])
    }
    return {number: len(members & allowed) for number, members in donor_index.items()}
