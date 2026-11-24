"""Extend the frozen exact named saved comparison to the staged DS30-0402 packet."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import exact_named_route as route


CASE = "0402"
STAGE = Path("/dev/shm/leo-v3-saved-0402-pair-01")
REQUEST = STAGE/"request.json"
EXACT_SHA256 = "8799f632207d4a1b65954e454766605dcad109a799b9b81a08158c3a2ebc26ff"
THREE_CASE_SHA256 = "1b78a16f6ca23ca7dad27db73b482aeda6ab1858343118d7e9815b5a7622385b"
PINS = {
    "request.json": "a2d730f64833eafd096877650e24b5c250b3bcfbef69d6bb5a44b70f0cbf1274",
    "stock-clock.json": "47f78189857d8d8a0a03a26cd2ef824fa467514d921fd967328fb22223d0ff63",
    "stock/saved-0402-worker.json": "77553815f450cb31b6469f915616f70e6157633caf6cc5fee9948edc31e3e997",
    "stock/joint-research-receipt.json": "865eb04161117f948ad3bccb6f6bfd3d5442acdc7d1edefcf03a65d441994633",
    "named-detections.json": "8fcd81df6bcbc3129b16b96de2109bf3ad22d2e306c5ccaca9383064f80f5d2c",
    "operator-offer.json": "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
}


def request_view(original):
    local, archive = original["local_archive"], original["original_archive"]
    if local["snapshots_sha256"] != archive["snapshots_sha256"]:
        raise ValueError("The local archive does not match the original signed causal inventory")
    return dict(original, local_archive=dict(local, snapshots=48))


def binding(case):
    if case != CASE or route.digest(Path(route.__file__)) != EXACT_SHA256:
        raise ValueError("Expected DS30-0402 on the frozen integrated exact named route")
    with patch.dict(route.CASES, {CASE: (6773, 6761, PINS, "named-0402")}):
        value = route.bind(case)
    for path in (Path(__file__), HERE/"exact-named-0402-protocol.md"):
        value["sources"][path.name] = route.digest(path)
    return value


def worker(root):
    value = binding(CASE)
    original = route.read
    request = request_view(original(REQUEST))

    def read(path):
        return request if path == REQUEST else original(path)

    with patch.object(route, "bind", return_value=value), patch.object(route, "read", read):
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
    if route.resident_path(root.parent) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh private tmpfs output")
    value = binding(CASE)
    _, refs = route.checked_catalogue(value, request_view(route.read(REQUEST)), TleArchiveReader, canonical_digest)
    res = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(r.path for r in refs)], text=True))["fincore"]
    if len(res) != len(refs) or any(row["res"] < row["size"] for row in res):
        raise ValueError("Every signed snapshot must already be resident")
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for path in (STAGE/"fonts").glob("fontlist-*.json"):
        os.link(route.resident_path(path), root/"fonts"/path.name)
    command = ["/usr/bin/timeout", "--kill-after=2s", "125s", RELEASE/"venv/bin/python", "-IB", __file__, "worker", root]
    write(root/"binding.json", dict(input=value, machine=machine, command=list(map(str, command)),
          resident_bytes=sum(row["size"] for row in res), resident_snapshots=len(refs), copied_inputs=0))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    write(root/"clock.json", measure(command, env, root/"candidate"))


def score(root):
    import exact_named_route_score as compare

    with patch.object(compare, "bind", binding):
        compare.verify(CASE, root)


def extend_panel(previous, candidate, digest):
    from exact_named_dense import reduce_panel

    recorded = previous["per_case"]
    if (set(recorded) != {"DS30-0160", "DS30-0316", "DS30-0374"}
            or candidate["case"] != "DS30-0402" or not candidate["exact"]
            or not all(all(row["parity"].values()) for row in (*recorded.values(), candidate))):
        raise ValueError("Requires exact parity on the three frozen comparisons and the sole new transfer")
    extra = {field: candidate[field] for field in ("clocks", "speedup", "geography", "parity")}
    rows = recorded | {candidate["case"]: extra}
    return dict(previous, recordings=len(rows), exact_cases=len(rows), per_case=rows,
                saved=reduce_panel(list(rows.values()), target=previous["target"]),
                prior_panel_sha256=THREE_CASE_SHA256, fourth_receipt_sha256=digest,
                new_gate_work=candidate["ports"]["gates"])


def aggregate(root):
    previous = HERE/"measurements/exact-named-saved-panel.json"
    if route.digest(previous) != THREE_CASE_SHA256:
        raise ValueError("The frozen three-comparison receipt differs")
    current = root/"result.json"
    result = extend_panel(route.read(previous), route.read(current), route.digest(current))
    with (root/"panel.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "worker", "score", "aggregate"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "worker": worker, "score": score, "aggregate": aggregate}[args.mode](args.root)
