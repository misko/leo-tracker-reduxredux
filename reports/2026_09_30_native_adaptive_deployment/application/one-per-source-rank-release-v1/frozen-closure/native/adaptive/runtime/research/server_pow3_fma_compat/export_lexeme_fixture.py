#!/usr/bin/env python3
import json
import re
import sys


MOMENTS = re.compile(
    r'"factorial_support_moments_s":\[([^,]+),([^,]+),([^,]+),([^\]]+)\]'
)

if len(sys.argv) not in (3, 4):
    raise SystemExit(
        "usage: export_lexeme_fixture.py PROJECTION.jsonl OUTPUT.tsv [GRAPH.tsv]"
    )

rows = retained = 0
authority = {}
with open(sys.argv[1], encoding="utf-8") as source, open(
    sys.argv[2], "w", encoding="utf-8"
) as output:
    for line in source:
        rows += 1
        record = json.loads(line)
        expected = record.get("expected")
        match = MOMENTS.search(line)
        if expected is None:
            if match is not None:
                raise RuntimeError("unavailable row contains support moments")
            output.write("unavailable\n")
            continue
        if match is None:
            raise RuntimeError("retained row lacks raw support-moment tokens")
        moment2 = match.group(3)
        moment3 = match.group(4)
        # The raw canonical-JSON tokens are the authority under test.  Confirm
        # the reference interpreter reads and re-emits each with float repr.
        if repr(expected["factorial_support_moments_s"][2]) != moment2:
            raise RuntimeError("moment2 token is not Python float repr")
        if repr(expected["factorial_support_moments_s"][3]) != moment3:
            raise RuntimeError("moment3 token is not Python float repr")
        output.write(f'{expected["candidate_id"]}\t{moment2}\t{moment3}\n')
        authority[expected["candidate_id"]] = (moment2, moment3)
        retained += 1

if rows != 24_681 or retained != 11_747:
    raise RuntimeError(f"unexpected fixture cardinality: {rows} rows, {retained} retained")

if len(sys.argv) == 4:
    graph = {}
    with open(sys.argv[3], encoding="utf-8") as source:
        if not source.readline().startswith("META\t"):
            raise RuntimeError("graph metadata is absent")
        if not source.readline().startswith("candidate_id\t"):
            raise RuntimeError("graph header is absent")
        for line in source:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 8 or fields[0] in graph:
                raise RuntimeError("invalid graph authority row")
            graph[fields[0]] = (fields[6], fields[7])
    if graph != authority:
        raise RuntimeError("graph authority moment lexemes differ")
