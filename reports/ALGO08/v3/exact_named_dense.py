"""Enroll the preregistered dense signed packet on the frozen exact solver."""

import argparse
import gzip
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import exact_named_route as route


CASE = "0374"
STAGE = Path("/dev/shm/leo-v3-0374-final-fit-result02")
WORKER = "named-final-0374-worker.json"
PAIR = HERE/"measurements/successor-DS30-0374-pair.json"
PAIR_SHA256 = "b49af1ff154c7123574ffe6190e394c2d4ed7e29ea3da8d0da6dce479f3be82b"
SOURCE_SHA256 = "92647ce638a4201bddcc9f5fd9ca757142bd24f26717fc24770c1975807aa071"
PINS = {
    "request.json": "72ced1ad90e5d9b6783efd20d6de6cf19edcb054bf445633d00b2b0f99cc454f",
    "inventory.json": "657d0d8d300647c2e7a8d548ae0ff9bb355dad50fe249950c629d1e2ebd835c4",
    "stock-clock.json": "637173124604f4b77411f8aaa80aac2b08a924371cfdee607d102b739fc245e0",
    f"stock/{WORKER}": "c8d5cdf833cfaf2b8fbc3c1229c476596b1f2c63090991117a97c273a39aa525",
    "stock/joint-research-receipt.json": "8bbbdb16a33302a90bb2147836ce1866d9ed3f503925d13677b361c9cd812564",
    "named-detections.json": "625adbd4e7601afd026f8b5d111e5daf3355727e63f28923058a69cddc9c933d",
    "operator-offer.json": "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
}
EARLIER = {
    "0160": "dd1f4a2f3891bba9a5ae9985f87273117223b137e398f39334e5b6edb3e1016b",
    "0316": "f53bfaad5a6b849398dce78bd7669c6d845f6bd886474a96ce71981c49464bc8",
}
EXPORT_SHA256 = "ea78ecc07d20b61b5f3473d08f849efe178df093c53c095fa9a7a0d6152993f2"


def request_view(request, authority):
    archive = request["local_archive"]
    if (authority["snapshots_sha256"] != archive["snapshots_sha256"]
            or not isinstance(archive["logical_bytes"], int) or archive["logical_bytes"] <= 0):
        raise ValueError("Original dense request and signed causal catalogue differ")
    return dict(request, original_archive=authority, local_archive=dict(archive, bytes=archive["logical_bytes"]))


def binding(case):
    from exact_solver_0057 import ARTIFACT, ARTIFACT_SHA, PRODUCER_SHA

    if case != CASE or route.digest(Path(route.__file__)) != SOURCE_SHA256 or route.digest(PAIR) != PAIR_SHA256:
        raise ValueError("Expected the frozen f4370e443 exact solver and original DS30-0374 receipt")
    verification = {STAGE/name: pin for name, pin in PINS.items()}
    producer = ARTIFACT.parent/"artifact-bind.json"
    verification.update({ARTIFACT: ARTIFACT_SHA[7:], producer: PRODUCER_SHA})
    for path, expected in verification.items():
        if route.digest(route.resident_path(path)) != expected:
            raise ValueError(f"Previously signed local file changed at {path}")
    request = route.read(STAGE/"request.json")
    pair = route.read(PAIR)
    source = route.read(producer)["source"]
    if (request["case"] != "DS30-"+CASE or request["recording"] != pair["recording"]
            or request["original_pair_sha256"] != PAIR_SHA256 or request["native_sha256"] != PINS["named-detections.json"]
            or request["inventory"] != "sha256:"+PINS["inventory.json"] or request["offer_sha256"] != PINS["operator-offer.json"]
            or source["cutoff_utc_ns"] >= request["causal_cutoff_utc_ns"]
            or Path(request["local_archive"]["root"]) != STAGE/"tle"):
        raise ValueError("Recording, offer, inventory, native packet or earlier causal producer changed")
    req = request_view(request, pair["archive"])
    sources = {p.name: route.digest(p) for p in (*route.SOURCES, Path(__file__), HERE/"exact-named-dense-protocol.md")}
    bound = dict(case=request["case"], stage=str(STAGE), request=str(STAGE/"request.json"), archive=str(STAGE/"tle"),
                 inventory=str(STAGE/"inventory.json"), packets={str(p): pin for p, pin in verification.items()},
                 original_pair=PAIR_SHA256, issued=request["issued"], admitted=request["admitted"], sources=sources,
                 portable=[str(ARTIFACT), ARTIFACT_SHA, PRODUCER_SHA])
    return bound, req


def worker(root):
    bound, request = binding(CASE)
    read = route.read

    def local(path):
        return request if path == STAGE/"request.json" else read(path)

    with patch.object(route, "bind", return_value=bound), patch.object(route, "read", local):
        route.worker(CASE, root)


def launch(root):
    from aperture_trial import RELEASE, write

    sys.path.extend((str(ROOT/"src"), str(RELEASE/"src")))
    from dense_geographic_trial import host
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure

    machine = host()
    bound, request = binding(CASE)
    _, refs = route.checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
    res = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(r.path for r in refs)], text=True))["fincore"]
    if len(res) != len(refs) or any(row["res"] < row["size"] for row in res):
        raise ValueError("The complete signed 47-source catalogue must already be resident")
    if route.resident_path(root.parent) != Path("/dev/shm") or root.exists():
        raise ValueError("A fresh canonical tmpfs result directory is required")
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for file in (STAGE/"fonts").glob("fontlist-*.json"):
        os.link(route.resident_path(file), root/"fonts"/file.name)
    command = ["/usr/bin/timeout", "--kill-after=2s", "90s", RELEASE/"venv/bin/python", "-IB", __file__, "worker", root]
    write(root/"binding.json", dict(input=bound, machine=machine, command=list(map(str, command)),
          resident_bytes=sum(row["size"] for row in res), resident_snapshots=len(refs), copied_inputs=0))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    write(root/"clock.json", measure(command, env, root/"candidate"))


def score(root):
    sys.path.insert(0, str(ROOT/"src"))
    import exact_named_route_score as comparison

    bound, _ = binding(CASE)
    verify, read = comparison.verified, comparison.read

    def historical_clock(path):
        document = read(path)
        return {"timing": document} if path == STAGE/"stock-clock.json" else document

    def original(root, clock, filename, request):
        named = filename == "saved-0374-worker.json"
        result = verify(root, clock, WORKER if named else filename, request)
        if named:
            historical = read(PAIR)["runs"]["baseline"]
            science = result["science"]
            if (any(science[k] != historical[k] for k in ("arms", "owners", "raw_authority", "scientific_digests", "artifacts"))
                    or science["receipt"]["terminal_sha256"] != historical["receipt"]["terminal_sha256"]
                    or {k: p["sha256"] for k, p in result["products"]["images"].items()} != historical["witnesses"]["pngs"]):
                raise ValueError("Saved named control does not reproduce the original release")
        return result

    with (patch.object(comparison, "bind", return_value=bound), patch.object(comparison, "read", historical_clock),
          patch.object(comparison, "verified", original)):
        comparison.verify(CASE, root)


def reduce_panel(cases, target=1.6):
    panel = {}
    for metric in ("elapsed_s", "cpu_s"):
        named = sum(row["clocks"]["named"][metric] for row in cases)
        candidate = sum(row["clocks"]["candidate"][metric] for row in cases)
        ratios = [row["speedup"][metric] for row in cases]
        typical = median(ratios)
        panel[metric] = dict(named_total_s=named, candidate_total_s=candidate, total_ratio=named/candidate,
                             median_ratio=typical, case_target_count=sum(value >= target for value in ratios),
                             total_target_met=named/candidate >= target, median_target_met=typical >= target)
    return panel


def aggregate(root):
    from hashlib import sha256

    cases = []
    for case, expected in EARLIER.items():
        payload = gzip.decompress((HERE/f"measurements/exact-named-DS30-{case}.json.gz").read_bytes())
        if sha256(payload).hexdigest() != expected:
            raise ValueError("Earlier one-recording exact evidence changed")
        cases.append(json.loads(payload))
    dense = route.read(root/"result.json")
    cases.append(dense)
    if not all(row["exact"] for row in cases):
        raise ValueError("Panel aggregation requires both calibration arms and full exact publication on every case")
    index = Path(dense["enrollment"]["input"]["portable"][0]).parent/"dense-export-clock.json"
    if route.digest(route.resident_path(index)) != EXPORT_SHA256:
        raise ValueError("Earlier standalone index first-use cost changed")
    failed = route.read(HERE/"measurements/exact-named-0316-rejected-startup.json")
    original = route.read(PAIR)["runs"]["baseline"]
    results = dict(recordings=len(cases), target=1.6, exact_cases=sum(row["exact"] for row in cases),
                   per_case={row["case"]: {key: row[key] for key in ("clocks", "speedup", "geography", "parity")} for row in cases},
                   saved=reduce_panel(cases), rejected_setup=failed, earlier_standalone_export=route.read(index),
                   raw_named_context={"dataset": "DS30-0374", "elapsed_s": original["elapsed_s"], "cpu_s": original["cpu_s"]},
                   dense_receipt_sha256=route.digest(root/"result.json"), earlier_receipts=EARLIER)
    with (root/"panel.json").open("x") as output:
        json.dump(results, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "worker", "score", "aggregate"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "worker": worker, "score": score, "aggregate": aggregate}[args.mode](args.root)
