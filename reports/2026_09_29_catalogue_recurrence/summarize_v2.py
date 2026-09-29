"""Raw-line auditor with explicit Alpha-5 decoding; scientific outputs unchanged."""

import summarize


def number(field):
    if len(field) != 5:
        raise ValueError("Require five-column catalogue field")
    if field.isdigit():
        return int(field)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    if field[0] not in alphabet or not field[1:].isdigit():
        raise ValueError("Invalid Alpha-5 field")
    return (10 + alphabet.index(field[0])) * 10000 + int(field[1:])


def raw_roster(payload):
    lines = [line.rstrip() for line in payload.splitlines() if line.strip()]
    numbers = []
    excluded = 0
    offset = 0
    while offset < len(lines):
        name = ""
        if not lines[offset].startswith("1 "):
            name = lines[offset].removeprefix("0 ").strip()
            offset += 1
        a, b = lines[offset : offset + 2]
        assert a.startswith("1 ") and b.startswith("2 ") and a[2:7] == b[2:7]
        decoded = number(a[2:7])
        if name.upper().startswith("STARLINK") and name.upper().endswith(" DEB"):
            excluded += 1
        else:
            numbers.append(decoded)
        offset += 2
    return numbers, excluded


if __name__ == "__main__":
    summarize.raw_roster = raw_roster
    summarize.main()
