"""Evaluate a fixed face contact rule on already sealed public science sidecars."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path
from time import process_time_ns

from leo.analysis.position_grid import ARMS
from leo.contracts.digests import canonical_digest
from leo.contracts.digests import sha256_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
from tools.pipeline_eval.scoring import distance_km
from tools.pipeline_eval.variants.experimental import grid_face_abstention as gate

HERE = Path(__file__).resolve().parent
REGIONAL = HERE.parent / "regional-release"
MEASUREMENTS = HERE / "measurements"
TMPFS = (Path("/tmp"), Path("/dev/shm"))
NORTH = Path("/tmp/leo-algo08v2-2x-bench")
SOUTH = Path("/dev/shm/leo-v3-named-south-transfer-01")
ORIGINAL = Path("/tmp/leo-regional-qZJKBw4W/outputs/blind")
NORTH_RECEIPTS = {
    "inside": ("combined-q15-repair-north-inside",
               "1c56f69ed889e6f29a50f6c5e411ce72b613f709bcc029552b6fcc54792ce3f3"),
    "outside": ("combined-q15-repair-north-edge-omitted",
                "26ffd21419368b5ea979603f730ac8dd572ccd68df871ee9883dbd0871913aa0"),
}
SOUTH_RECEIPTS = {
    "inside": ("containing", "25a311334c51296e81176c23fe7609b78b1262c7a600da2e5a2a6eed0d029195"),
    "outside": ("near-omitted", "d4e46271bf683017213c2c70df065e0bcb8192ef45ba7f09efb0cd840bf48cb0"),
}
ORIGINAL_OFFERS = {
    "north-wide": "ee38c830e4ef729648b6778f",
    "north-omitted": "5ce94c3e4020fb8154463bf8",
    "south-wide": "d42b15f61b87f12a9ba43a39",
    "south-omitted": "5ce4e400ce75ee00381555ce",
}
SITES = {"north": "0abe7b4514be674d9f5388e3", "south": "6bd1f26bfa0bedfcf3f100f8"}
COMMON_ORBIT_HIST = "sha256:7aa06cab0502bcac70645a41a219bb6d53f1077f329e6f7ed79eb59a8794feec"
PUBLIC_PREDICTIONS_PIN = "46e8925aad5b047b89f57b95d22581a5eca4dfc52f3196790154c01bdc340549"
PUBLIC_KEY_PIN = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
SOUTH_PIN = "de1cbf1f6729191eff8cc0af316be0979e2349507795a8fb921bef40e38bcee2"


def staged(path):
    path = path.resolve(strict=True)
    if not any(path.is_relative_to(root) for root in TMPFS):
        raise ValueError(f"Read only staged tmpfs publication metadata: {path}")
    return path


def pinned(path, expected):
    data = staged(path).read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Published receipt digest changed: {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def write(path, value):
    with path.open("x") as stream:
        print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), file=stream)


def normalized_science(document):
    return canonical_digest({k: v for k, v in document.items()
                             if k not in ("binding", "elapsed_seconds")})


def load_publication(root, receipt, *, digests=None, scrub=False):
    root = staged(root)
    run_id = receipt["run_id"]
    path = FastScanStore(root).automatic_workspace(run_id, create=False) / "terminal.json"
    terminal = json.loads(staged(path).read_bytes())
    if (
        canonical_digest(terminal) != receipt["terminal_sha256"]
        or terminal["session_id"] != receipt["session_id"] or terminal["region"] != receipt["region"]
        or terminal["decision"] != "ok" or receipt["decision"] != "complete"
    ):
        raise ValueError("Published receipt and terminal do not match")
    if "arms" in receipt and terminal["arms"] != receipt["arms"]:
        raise ValueError("Published indexed arm positions differ from the terminal")

    store = FastStandardAnalysisStore(root)
    for filename in ("manifest.json", "position-path.json", "position-grid.json"):
        sidecar = store.folder(run_id) / filename
        if sidecar.exists():
            staged(sidecar)
    grid, path = store.position_grid(run_id), store.position_path(run_id)
    identity = {key: terminal[key] for key in ("region", "session_id", "arms", "native_sha256",
                                                "orbit_policy")}
    identity["terminal_sha256"] = receipt["terminal_sha256"]
    if grid is None or path is None:
        return identity, {"state": "unassessable", "reason": "missing_grid_or_path"}

    for name, document in (("path", path), ("grid", grid)):
        if (document["binding"]["input_sha256"] != terminal["native_sha256"]
                or document["binding"]["terminal_sha256"] != receipt["terminal_sha256"]):
            raise ValueError("Published position evidence does not bind the exact terminal input")
        science = normalized_science(document) if scrub else canonical_digest(document)
        if digests is not None and digests[name] != science:
            raise ValueError(f"Published {name} differs from the original paired receipt")
        identity[f"{name}_sha256"] = canonical_digest(document)
    identity["owner_sha256"] = grid["binding"]["owner_sha256"]
    endpoints = {arm: path["stages"][-1]["arms"][arm]["endpoint"] for arm in ARMS}
    if grid["endpoints"] != endpoints or grid["endpoint_latlon"] != {
        arm: terminal["arms"][arm]["latlon"] for arm in ARMS
    }:
        raise ValueError("Final position path and grid endpoints differ from signed positions")
    began = process_time_ns()
    result = gate.face_contact(grid)
    result.update(readout_cpu_ns=process_time_ns() - began, evaluated_points=grid["evaluated_points"])
    return identity, result


def verify_pairs(cases):
    pairs = (("south-inside", "south-outside"), ("north-inside", "north-outside"),
             ("north-wide", "north-omitted"), ("south-wide", "south-omitted"))
    for first, second in pairs:
        left, right = (cases[name]["identity"] for name in (first, second))
        keys = ("native_sha256", "session_id", "orbit_policy")
        if any(left[key] != right[key] for key in keys):
            raise ValueError(f"Expected matched detector inputs and sky policy for {first}/{second}")


def named_south_authority():
    source = pinned(MEASUREMENTS / "named-south-transfer.json.gz", SOUTH_PIN)
    return source["seal"]["inputs"]


def run(output):
    result = {}
    for condition, (name, digest) in NORTH_RECEIPTS.items():
        pin = pinned(NORTH / f"{name}.json", digest)
        if pin["archive"]["snapshots_sha256"] != COMMON_ORBIT_HIST:
            raise ValueError("Unexpected northern original causal archive")
        source = pin["run"]
        identity, decision = load_publication(
            NORTH / name, source["receipt"], digests=source["scientific_digests"], scrub=True,
        )
        if identity["arms"] != source["arms"]:
            raise ValueError("Northern seal did not bind the archived calibration arms")
        result[f"north-{condition}"] = {
            "identity": identity, "readout": decision, "source_sha256": digest,
            "build": pin["spec"], "archive_sha256": COMMON_ORBIT_HIST,
        }
    south_inputs = named_south_authority()
    for condition, (name, digest) in SOUTH_RECEIPTS.items():
        directory = SOUTH / name
        source = pinned(directory / "joint-research-receipt.json", digest)
        identity, decision = load_publication(
            directory, source["receipt"], digests=source["evidence"],
        )
        inputs = south_inputs[name]
        if (
            identity["native_sha256"] != inputs["native"] or identity["session_id"] != inputs["session"]
            or inputs["archive"]["snapshots_sha256"] != COMMON_ORBIT_HIST
        ):
            raise ValueError("Named-survivor South seal has different detector or sky authority")
        result[f"south-{condition}"] = {
            "identity": identity, "readout": decision, "source_sha256": digest,
            "build": "named-survivor South transfer", "scientific_seal_sha256": SOUTH_PIN,
            "sealed_inputs_sha256": canonical_digest(south_inputs),
        }
    public = pinned(REGIONAL / "predictions.json", PUBLIC_PREDICTIONS_PIN)
    by_offer = {row["offer"]: row for row in public["rows"]}
    for name, offer_id in ORIGINAL_OFFERS.items():
        source = by_offer[offer_id]
        identity, decision = load_publication(ORIGINAL, source)
        result[name] = {
            "identity": identity, "readout": decision, "source_sha256": PUBLIC_PREDICTIONS_PIN,
            "build": "original regional v2",
        }
    verify_pairs(result)
    write(output, {"threshold": gate.LEVEL, "cases": result})


def score(input_path, output):
    data = json.loads(staged(input_path).read_bytes())
    if data.get("threshold") != gate.LEVEL:
        raise ValueError("The prediction threshold differs from the frozen protocol")
    key = pinned(REGIONAL / "scoring-key.json", PUBLIC_KEY_PIN)["answers"]
    truth = {}
    for site, recording in SITES.items():
        truth[site], = {tuple(row["truth"]) for row in key.values() if row["recording"] == recording}
    values = {arm: {} for arm in (*ARMS, "paired", "both")}
    for name, case in data["cases"].items():
        site = name.split("-")[0]
        identity, readout = case["identity"], case["readout"]
        clearance = face_clearance_km(identity["region"], truth[site])
        case["truth_clearance_km"] = clearance
        case["errors"] = {arm: distance_km(row["latlon"], truth[site])
                          for arm, row in identity["arms"].items()}
        if readout["state"] != "assessable":
            continue
        for arm in ARMS:
            values[arm][name] = readout["arms"][arm]["gap"]
        for variant in ("paired", "both"):
            values[variant][name] = readout[f"{variant}_gap"]
    trials = {}
    for method, rows in values.items():
        containing = {name: gap for name, gap in rows.items()
                      if data["cases"][name]["truth_clearance_km"] >= 0}
        omitted = {name: gap for name, gap in rows.items() if name not in containing}
        all_interval = (
            gate.separating_interval(containing.values(), omitted.values())
            if containing and omitted else None
        )
        south_interval = (
            gate.separating_interval([containing["south-inside"]], [omitted["south-outside"]])
            if "south-inside" in containing and "south-outside" in omitted else None
        )
        trials[method] = {
            "containing_false_abstentions": [
                name for name, gap in containing.items() if gap <= gate.LEVEL
            ],
            "omitted_abstentions": [name for name, gap in omitted.items() if gap <= gate.LEVEL],
            "assessable_containing": len(containing), "assessable_omitted": len(omitted),
            "all_offer_interval": all_interval, "south_pair_interval": south_interval,
        }
    write(output, dict(data, input_sha256=sha256_digest(staged(input_path).read_bytes()),
                       truth_sha256=PUBLIC_KEY_PIN, decisions=trials))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="method", required=True)
    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("output", type=Path)
    score_cmd = sub.add_parser("score")
    score_cmd.add_argument("input_path", type=Path)
    score_cmd.add_argument("output", type=Path)
    options = vars(parser.parse_args())
    (run if options.pop("method") == "run" else score)(**options)


if __name__ == "__main__":
    main()
