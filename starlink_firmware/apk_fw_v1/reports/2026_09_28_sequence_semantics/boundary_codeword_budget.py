"""Test a restricted header-plus-one-MCS carrier budget, without offset fitting."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def candidates(boundary, records):
    matches = []
    for units in range(1, 17):
        remaining = boundary - 114 * units
        for record in records:
            width = record["symbols_per_codeword"]
            if remaining > 0 and remaining % width == 0:
                matches.append(
                    dict(
                        header_units=units,
                        mcs=record["identifier"],
                        codewords=remaining // width,
                        symbols_per_codeword=width,
                    )
                )
    return matches


def main():
    boundary_path = BASE / "local/soft_tail_boundary.json"
    table_path = (
        BASE.parents[3]
        / "starlink_firmware/apk_fw_v1/local/firmware"
        / "phy-modcod-table.json"
    )
    records = json.loads(table_path.read_text())["packed_word_inference"]
    rows = []
    for row in json.loads(boundary_path.read_text())["rows"]:
        if row["flank"] != 502:
            continue
        found = candidates(row["boundary"], records)
        rows.append(
            dict(
                frame=row["frame"],
                boundary=row["boundary"],
                matches=found,
                unique_budgets=len(
                    {(r["header_units"], r["symbols_per_codeword"], r["codewords"]) for r in found}
                ),
            )
        )
    output = dict(
        rows=rows,
        header_units=list(range(1, 17)),
        model="boundary = 114 * header_units + symbols_per_codeword * count",
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (boundary_path, table_path)
        },
        limitation="Restrictive exploratory model: one header, one payload MCS, "
        "whole codewords, no prefix/gap/other overhead, compact carrier count "
        "assumed to equal firmware symbol units. Header-unit range is an "
        "assay bound, not a proven RF header limit. Firmware generation differs "
        "from recording. Numerical match is not a decoded header or payload.",
    )
    (BASE / "local/boundary_codeword_budget.json").write_text(json.dumps(output, indent=2) + "\n")
    for row in rows:
        print(row["frame"], len(row["matches"]), row["unique_budgets"])


if __name__ == "__main__":
    main()
