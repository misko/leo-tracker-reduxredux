"""Join the already selected anchor-cycle routes to their archived publications."""

import argparse
from gzip import decompress
import json
from pathlib import Path

from anchor_cycle_route import CASES, HERE
from aperture_trial import read, write
from dense_full_short_raw import checked
from leo.contracts.digests import canonical_digest


BENCH = Path("/tmp/leo-algo08v2-2x-bench")
NORTH = Path("/var/tmp/leo-north-short-regional-nov23")
NORTH_HISTORY = Path("/var/tmp/leo-north-short-causal-raw-nov23")
TRANSFER = Path("/var/tmp/leo-causal-weak-south-nov23")
MEDIUM_CONTROL = Path("/tmp/leo-protected-DS30-0057-01")
OMITTED_HISTORY = Path("/var/tmp/leo-local-future-omissions.kwn5FsYr/paired")
SOUTH_EXTERIOR = Path("/var/tmp/leo-regional-track.O238AD0C")
OFFER_PINS = {"north": "283375bbad24eee8a0871a7e878c906fd1471158e7ff070d913f9be8d1267dd7",
              "south": "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9"}
CONTAINING = {
    "north": (NORTH / "stock", NORTH / "containing", NORTH_HISTORY / "containing"),
    "DS30-0016": (Path("/dev/shm/leo-v3-combined-frontier-weak-03/stock"), CASES["DS30-0016"][0], TRANSFER / "physical"),
    "south": (BENCH / "exact-curved-lookahead-south-inside/baseline", Path("/var/tmp/leo-short-graph-20261123-south-inside"),
              TRANSFER / "south-inside"),
    "DS30-0057": (MEDIUM_CONTROL / "stock", CASES["DS30-0057"][0], MEDIUM_CONTROL / "forward"),
}
MISSING = {
    "north_near": (NORTH / "north-mirror-outside", NORTH_HISTORY / "north-mirror-outside"),
    "north_far": (NORTH / "north-far", NORTH_HISTORY / "north-far"),
    "south_near": (SOUTH_EXTERIOR / "south-near", OMITTED_HISTORY / "south-near-forward"),
    "south_far": (SOUTH_EXTERIOR / "south-far", OMITTED_HISTORY / "south-far-forward"),
}


def publication(root):
    (terminal_path,) = (root / "fast-scan-automatic-work").glob("*/terminal.json")
    terminal = read(terminal_path)
    proof = dict(root=str(root), terminal_sha256=canonical_digest(terminal), input=terminal["native_sha256"],
                 offer=terminal["region"], decision=terminal["decision"], arms=terminal["arms"])
    if terminal["decision"] == "ok":
        (path,) = (root / "fast-scan-standard-v2" / terminal_path.parent.name).glob("*/manifest.json")
        manifest = read(path)
        if (manifest["terminal_sha256"] != proof["terminal_sha256"] or manifest["input_sha256"] != proof["input"]
                or manifest["state"] != "complete" or manifest["region"] != proof["offer"] or len(manifest["artifacts"]) != 8):
            raise ValueError(f"Expected a complete sealed publication at {root}")
        proof["owners"] = {arm: {key: row[key] for key in ("owner_sha256", "associated_points")}
                           for arm, row in manifest["arms"].items()}
        proof["matched_owners_between_arms"] = proof["owners"]["c0"] == proof["owners"]["fitted_c"]
        proof["figure_count"] = len(manifest["artifacts"])
    return proof


def main(scores, output):
    data = read(scores)
    medium_receipt = checked(HERE / "measurements/local-future-0057.json.gz", "217fcc7ba7bbc95056ed64696c7444898138c268dbad4ced3c3f3f557f42727f")
    medium_policy = json.loads(decompress(medium_receipt.read_bytes()))["policy"]
    joined = {}
    for case, assessment in data["cases"].items():
        names = ("v3", "unfiltered", "history")
        runs = dict(zip(names, map(publication, CONTAINING[case]), strict=True))
        if runs["unfiltered"]["input"] != assessment["input"]:
            raise ValueError(f"Sealed run did not use the routed input at {case}")
        history_digest = medium_policy["forward_sha256"] if case == "DS30-0057" else runs["history"]["input"]
        if history_digest != assessment["restored_history"] or any(r["offer"] != runs["v3"]["offer"] for r in runs.values()):
            raise ValueError(f"History or offer differs at {case}")
        for name in ("unfiltered", "history"):
            expected_rms = data["revealed"][case]["reference"][f"{name}_rf_rms_hz"]
            if any(abs(runs[name]["arms"][arm]["rf_rms_hz"] - rms) > 1e-8
                   for arm, rms in zip(("c0", "fitted_c"), expected_rms, strict=True)):
                raise ValueError(f"The containing publication differs from the original scored {case} {name} route")
        joined[case] = dict(containing=runs, verified_history_input=history_digest, selected=assessment["route"])
    for key, roots in MISSING.items():
        site, length = key.split("_")
        archived = read(checked(BENCH / f"exact-curved-lookahead-{site}-offers.json", OFFER_PINS[site]))
        name = "far" if length == "far" else "mirror-outside"
        stock = archived["results"][f"{site}-{name}"]
        unfiltered, history = map(publication, roots)
        history_digest = read(roots[1] / "forward-policy.json")["forward_sha256"] if site == "south" else history["input"]
        if (any(run["offer"] != stock["offer"] for run in (unfiltered, history))
                or unfiltered["input"] != data["cases"][site]["input"]
                or history_digest != joined[site]["verified_history_input"]):
            raise ValueError(f"Omission proofs differ in the original offered square or route at {key}")
        joined[site][length] = dict(v3=stock, unfiltered=unfiltered, history=history)
    write(output, dict(data, archived_publications=joined))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("scores", type=Path)
    cli.add_argument("output", type=Path)
    main(**vars(cli.parse_args()))
