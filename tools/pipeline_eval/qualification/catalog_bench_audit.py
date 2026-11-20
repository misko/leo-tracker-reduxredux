"""Compare exact checksum source and catalogue validation on the sealed snapshots."""

import ast
import json
import os
import runpy
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from catalog_bench_worker import CHECKSUM, code, definitions, digest, write_json

FIELDS = (
    "satnum",
    "satnum_str",
    "classification",
    "intldesg",
    "epochyr",
    "epochdays",
    "jdsatepoch",
    "jdsatepochF",
    "ndot",
    "nddot",
    "bstar",
    "inclo",
    "nodeo",
    "ecco",
    "argpo",
    "mo",
    "no_kozai",
    "ephtype",
    "elnum",
    "revnum",
    "error",
)


def outcome(operation, *args):
    try:
        return {"value": operation(*args)}
    except (ValueError, RuntimeError) as error:
        return {"error": type(error).__name__, "message": str(error)}


def fields(parser, text):
    catalogue = parser(text)
    h = sha256()
    for name, number, orbit in zip(
        catalogue.names, catalogue.satellite_numbers, catalogue.satellites, strict=True
    ):
        row = (name, number, *(getattr(orbit, field) for field in FIELDS))
        h.update(repr(row).encode() + b"\n")
    return dict(records=len(catalogue), fields_sha256=h.hexdigest())


def update(line, start, text, checksum):
    raw = line[:start] + text + line[start + len(text) : 68]
    return raw + str(checksum(raw))


def line_vectors(first):
    class RewrittenSlice(str):
        def __getitem__(self, key):
            return "-2" if isinstance(key, slice) else super().__getitem__(key)

    def pair(prefix, tail):
        return prefix + " " * (68 - len(prefix)) + tail

    return {
        "all_ascii_columns": "".join(chr(c) for c in range(128)),
        "only_last_included_column": " " * 67 + "9" + "8",
        "outside_checksum_prefix": pair("9", "²"),
        "unicode_decimal_prefix": pair("١９", "0"),
        "unicode_isdigit_without_int": pair("²", "0"),
        "unicode_minus_ignored": pair("−-", "0"),
        "rewrite_from_subclass_slice": RewrittenSlice(first),
        "empty": "",
    } | {f"ascii_{c}": chr(c) for c in range(128)}


def catalogue_vectors(first, second, checksum):
    pair = first + "\n" + second
    wrong = str((int(first[-1]) + 1) % 10)
    mismatched_second = update(second, 2, "99999", checksum)
    invalid = [update(line, 2, "A@001", checksum) for line in (first, second)]
    alpha5 = [update(line, 2, "A1234", checksum) for line in (first, second)]
    return {
        "two-line": pair,
        "zero-prefixed-name": "0 PROBE\n" + pair,
        "plain-name": "PROBE\n" + pair,
        "trailing-space-and-crlf": first + " \r\n" + second + " \r\n",
        "wrong-width": first[:-1] + "\n" + second,
        "wrong-prefix": first + "\n" + update(second, 0, "1", checksum),
        "non-digit-checksum": first[:-1] + "?\n" + second,
        "wrong-checksum": first[:-1] + wrong + "\n" + second,
        "wrong-checksum-after-valid-record": pair + "\n" + first[:-1] + wrong + "\n" + second,
        "different-catalogue-ids": first + "\n" + mismatched_second,
        "invalid-matching-catalogue-ids": "\n".join(invalid),
        "valid-alpha5": "\n".join(alpha5),
        "mid-record": first,
        "empty": " \n\n",
        "unicode-decimal-checksum": first[:-1] + chr(0x660 + int(first[-1])) + "\n" + second,
        "unicode-isdigit-checksum": first[:-1] + "²\n" + second,
        "unicode-isdigit-in-body": first[:67] + "²" + first[68:] + "\n" + second,
    }


def benchmark(lines, installed, candidate):
    controls = [installed(line) for line in lines]
    if [candidate(line) for line in lines] != controls:
        raise ValueError("an original archive checksum differs from the installed implementation")
    repetitions, total = [], sum(controls)
    methods = [("installed", installed), ("frozen_checksum", candidate)]
    for index in range(5):
        runs = {}
        for name, calculate in methods if index % 2 == 0 else reversed(methods):
            wall, cpu = perf_counter(), process_time()
            check = sum(map(calculate, lines))
            runs[name] = dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - wall)
            if check != total:
                raise ValueError("measured catalogue checksum changed")
        repetitions.append(runs)
    return dict(lines=len(lines), total=total, repetitions=repetitions)


def audit(work, lock, propagation, archive_type):
    checksum, source_receipt = code(work, lock, propagation)
    stock = propagation.element_line_checksum
    source = (work / "production-propagation.py").read_bytes()
    node = definitions(ast.parse(source))["parse_element_sets"]
    env = vars(propagation).copy() | {CHECKSUM: checksum}
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), "production-propagation.py", "exec"), env
    )
    production_parser = env["parse_element_sets"]

    def parse(text):
        standard = outcome(fields, propagation.parse_element_sets, text)
        with patch.object(propagation, CHECKSUM, checksum):
            candidate = outcome(fields, propagation.parse_element_sets, text)
            production = outcome(fields, production_parser, text)
        if standard != candidate:
            raise ValueError("isolated checksum changed strict catalogue validation")
        return dict(installed=standard, frozen_checksum=candidate, production=production)

    synthetic, catalogue, measurements = {}, {}, {}
    for ident in lock["sequence"]:
        spec = lock["cases"][ident]["spec"]
        rows = []
        archive = archive_type(Path(spec["archive"]))
        for snapshot in archive.list_snapshots():
            if snapshot.sha256 != spec["snapshots"][snapshot.path.name].removeprefix("sha256:"):
                raise ValueError("catalogue audit differs from the sealed recording")
            text = archive.read(snapshot)
            if not rows:
                lines = [s.rstrip() for s in text.splitlines() if s.startswith(("1 ", "2 "))]
                measurements[ident] = dict(
                    snapshot=snapshot.path.name, **benchmark(lines, stock, checksum)
                )
                if not synthetic:
                    first, second = lines[:2]
                    vectors = line_vectors(first)
                    line_results = {key: outcome(stock, value) for key, value in vectors.items()}
                    if line_results != {
                        key: outcome(checksum, value) for key, value in vectors.items()
                    }:
                        raise ValueError("line-level fallback behavior changed")
                    synthetic = dict(
                        lines=line_results,
                        catalogues={
                            key: parse(value)
                            for key, value in catalogue_vectors(first, second, stock).items()
                        },
                    )
            rows.append(dict(name=snapshot.path.name, sha256=snapshot.sha256, **parse(text)))
        if {row["name"] for row in rows} != set(spec["snapshots"]):
            raise ValueError("the catalogue reader failed to audit all sealed snapshots")
        catalogue[ident] = dict(
            catalogue_status=Counter(
                "accepted" if "value" in r["installed"] else "rejected" for r in rows
            ),
            production_differences=[r["name"] for r in rows if r["installed"] != r["production"]],
            rows=rows,
        )
    return dict(
        cpu=sorted(os.sched_getaffinity(0)),
        source=source_receipt,
        fields=list(FIELDS),
        source_lock_sha256=digest((work / "source-lock.json").read_bytes()),
        audit_program_sha256=digest(Path(__file__).read_bytes()),
        catalogues=catalogue,
        synthetic=synthetic,
        checksum_benchmark=measurements,
    )


def main():
    work, target = map(Path, sys.argv[1:])
    lock = json.loads((work / "source-lock.json").read_bytes())
    receiver = Path(lock["receiver"])
    entry = runpy.run_path(str(receiver / "__main__.py"))
    entry["activate"](receiver)
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky import propagation

    result = audit(work, lock, propagation, TleArchiveReader)
    entry["verify_project_modules"](receiver)
    write_json(target, result)


if __name__ == "__main__":
    main()
