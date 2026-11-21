"""Score candidate lists from a standalone receiver on the same signed stereo I/Q visits."""

import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
import zipfile
from collections import Counter
from contextlib import ExitStack
from pathlib import Path


def compatible(a, b):
    return (
        abs((a["epoch"] - b["epoch"] + 6666.5) % 13333 - 6666.5) <= 2
        and abs(a["hz"] - b["hz"]) <= 1000
    )


def matching(peaks, targets):
    """Match each measurement and each label at most once, maximizing the number of matches."""
    assigned = {}

    def connect(i, visited):
        for j, t in enumerate(targets):
            if j in visited or not compatible(peaks[i], t):
                continue
            visited.add(j)
            if j not in assigned or connect(assigned[j], visited):
                assigned[j] = i
                return True
        return False

    for i in range(len(peaks)):
        connect(i, set())
    return {i: j for j, i in assigned.items()}


def score(reference, inputs, binary, assets, panel, output):
    results = []
    with ExitStack() as stack:
        source = stack.enter_context(zipfile.ZipFile(reference))
        with source.open("scoring-roster.csv") as f, io.TextIOWrapper(f, newline="") as s:
            rows = list(csv.DictReader(s))
        chosen = [r for r in rows if r["panel"] == panel]
        if not chosen or len(chosen) != len({r["key"] for r in chosen}):
            raise ValueError("missing or duplicate scoring visits")
        raw = {}
        for path in inputs:
            z = stack.enter_context(zipfile.ZipFile(path))
            for r in json.loads(z.read("index.json"))["visits"]:
                if r["key"] in raw:
                    raise ValueError("duplicate physical I/Q in archives")
                raw[r["key"]] = z, r
        counts = Counter()
        for row in chosen:
            z, r = raw[row["key"]]
            iq = z.read(r["file"])
            if (
                r["sha256"] != row["iq"]
                or "sha256:" + hashlib.sha256(iq).hexdigest() != row["iq"]
                or len(iq) != 1600000
                or r["dtype"] != "<i2"
                or r["shape"] != [200000, 2, 2]
                or r["sample_rate_hz"] != 10000000
                or r["physical_id"] != row["id"]
                or int(row["counter"]) != r["hardware_sample_counter"]
                or r["edge"] != row["edge"]
                or r["evaluated_antenna"] != int(row["rx"])
            ):
                raise ValueError("raw I/Q or hardware identity mismatch")
            lo, hi = float(row["lo_hz"]), float(row["hi_hz"])
            cmd = [
                str(binary.resolve()),
                str(assets / (r["edge"] + ".f32")),
                "-",
                row["rx"],
                str(lo),
                str(hi),
            ]
            call = subprocess.run(cmd, input=iq, capture_output=True, timeout=30, check=True)
            peaks = json.loads(call.stdout)["candidates"]
            if len(peaks) > 32 or any(
                not (
                    math.isfinite(p["hz"])
                    and math.isfinite(p["epoch"])
                    and lo <= p["hz"] <= hi
                    and 0 <= p["epoch"] < 13333
                )
                for p in peaks
            ):
                raise ValueError("invalid signed carrier or frame time")
            refs = json.loads(row["targets"])
            hits = matching(peaks, refs)
            counts.update(
                visits=1,
                reference_peaks=len(refs),
                matches=len(hits),
                returns=len(peaks),
                multi_reference_visits=len(refs) > 1,
                all_recovered_multi=len(refs) > 1 and len(hits) == len(refs),
                unresolved_returns=not refs and bool(peaks),
            )
            results.append(dict(key=row["key"], peaks=peaks, targets=refs, matches=hits))
    if output:
        output.write_text(
            json.dumps(dict(panel=panel, counts=counts, visits=results), allow_nan=False) + "\n"
        )
    return dict(counts)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--iq", type=Path, nargs="+", required=True)
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument(
        "--panel",
        choices=(
            "prospective",
            "previous_fresh",
            "established",
            "recovery",
            "satellite",
            "roundtrip",
            "revised_roundtrip",
            "revised_satellite",
            "prospective_conditioned",
            "previous_fresh_conditioned",
            "established_conditioned",
            "recovery_conditioned",
            "physical",
        ),
        default="prospective",
    )
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    print(json.dumps(score(a.reference, a.iq, a.executable, a.assets, a.panel, a.output), indent=2))
