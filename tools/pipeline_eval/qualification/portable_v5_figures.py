"""Normalize the authenticated roof and synthetic portability receipts for charts."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import validate_result
from .full_v5_check import _load_case
from .portable_v5_transfer import MODES
from .portable_v5_trials import METHOD, REPORT, ROOF_CASE, checksum


def sealed_rows(path, rows):
    for row in rows:
        validate_result(row["result"])
    write(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))


def export_roof(report):
    row = json.loads((report / "roof-parity.json").read_bytes())
    if not row["identical"] or row["portable"]["result"]["arms"] != row["stock"]["result"]["arms"]:
        raise ValueError("roof figure requires confirmed same-input solver parity")
    data = _load_case(ROOF_CASE)
    binding = dict(
        native_sha256=data["native"]["sha256"],
        catalog_sha256=data["catalog"]["sha256"],
        history_sha256=row["portable"]["history_sha256"],
    )
    rows = {
        "roof-positions.jsonl.gz": dict(row["portable"], **binding),
        "roof-stock-positions.jsonl.gz": dict(row["stock"], method="orbit_projector", **binding),
    }
    for name, result in rows.items():
        if result["id"] != ROOF_CASE:
            raise ValueError("portable roof figure has a wrong case ID")
        sealed_rows(report / name, [result])
    save_json(
        report / "roof-figure-lock.json",
        dict(cases=[ROOF_CASE], files={name: checksum(report / name) for name in rows}),
    )


def export_transfer(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    source = {}
    for mode in MODES:
        path = report / f"{mode}.jsonl.gz"
        if checksum(path) != lock[mode]:
            raise ValueError("portability predictions changed after seal")
        with gzip.open(path, "rt") as stream:
            source[mode] = list(map(json.loads, stream))
    labels = json.loads((report / "synthetic-labels.json").read_bytes())["captures"]
    aliases = {r["id"]: f"synthetic-site-{i}" for i, r in enumerate(source[MODES[0]], 1)}
    rows, queries = [], []
    for mode in MODES:
        for raw in source[mode]:
            capture = raw["id"]
            ident = f"{capture}-{mode}"
            binding = {k: raw[k] for k in ("history_sha256", "document_sha256", "input_sha256")}
            condition = "present" if mode == MODES[0] else "missing"
            rows.append(dict(raw, id=ident, capture_id=capture, method=METHOD))
            queries.append(
                dict(
                    id=ident,
                    condition=condition,
                    recording=aliases[capture],
                    truth=labels[capture]["position"],
                    bindings=binding,
                )
            )
    sealed_rows(report / "synthetic-positions.jsonl.gz", rows)
    save_json(report / "figure-queries.json", dict(queries=queries))
    names = ("synthetic-positions.jsonl.gz", "figure-queries.json")
    save_json(
        report / "figure-lock.json",
        dict(
            cases=[r["id"] for r in rows], files={name: checksum(report / name) for name in names}
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=("roof", "transfer"))
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    (export_roof if args.panel == "roof" else export_transfer)(local_output(args.report))


if __name__ == "__main__":
    main()
