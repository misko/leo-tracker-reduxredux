"""Export the individual modification charts and their plotted observations in one ZIP."""

import argparse
import csv
import io
import re
from dataclasses import asdict, replace
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from ..__main__ import ROOT, local_output, write
from . import acquisition_index as index


def table(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def observations(panels, paths):
    data, found = [], set()
    for path in paths:
        seen = set()
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                key = row["arm"], row["figure"]
                if key in panels:
                    seen.add(key)
                    data.append(row)
        if seen & found:
            raise ValueError("a position panel has more than one source table")
        found.update(seen)
    if found != panels:
        raise ValueError(f"plotted observations missing for {sorted(panels - found)}")
    return table(data)


def archive(root, rows, data):
    files = {
        "positions.csv": data,
        "detector-stages.pdf": (root / "stage-charts/stage-evidence.pdf").read_bytes(),
    }
    local_rows = []
    for row in rows:
        if (
            row.state != "Chart ready"
            or row.arm not in {*index.ARMS, "stage"}
            or not re.fullmatch(r"[\w-]+", row.panel_id)
            or Path(row.chart).suffix != ".png"
        ):
            raise ValueError(f"panel lacks a ready PNG or a valid export name: {row.panel_id}")
        name = f"{row.arm}/{row.panel_id}.png"
        if name in files:
            raise ValueError(f"duplicate chart in ZIP: {name}")
        files[name] = (root / row.chart).read_bytes()
        evidence = "detector-stages.pdf" if row.arm == "stage" else "positions.csv"
        local_rows.append(replace(row, chart=name, evidence=evidence, report=""))
    files["chart-inventory.csv"] = table([asdict(row) for row in local_rows])
    files["index.html"] = index.page(
        local_rows,
        {"Per-recording errors": "positions.csv", "Detector stages": "detector-stages.pdf"},
    ).encode()
    out = io.BytesIO()
    with ZipFile(out, "w") as result:
        for name, content in sorted(files.items()):
            result.writestr(ZipInfo(name), content, compress_type=ZIP_DEFLATED)
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=local_output)
    args = parser.parse_args()
    root, atlas = index.ACQUISITION, index.ATLAS
    rows = index.inventory(root, atlas, ROOT)
    panels = {(row.arm, row.panel_id) for row in rows if row.arm != "stage"}
    paths = [
        path
        for arm in index.ARMS
        for path in (
            root / "charts" / arm / "modifications.csv",
            root / "charts" / arm / "transfer.csv",
            atlas / "roof" / arm / "original-ten.csv",
            root.parent / "streamlined/charts" / arm / "modifications.csv",
        )
    ]
    write(args.out, archive(root, rows, observations(panels, paths)))
    print(f"{len(rows)} individual PNGs and their index in {args.out}")


if __name__ == "__main__":
    main()
