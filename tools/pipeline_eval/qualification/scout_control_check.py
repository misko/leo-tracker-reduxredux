"""Independently audit sealed whole-waveform four-start control repetitions."""

import argparse
import gzip
import json
import struct
from collections import Counter
from hashlib import sha256
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, coordinate, distance_km
from . import fresh_waveform, whole_band_results
from .full_v5_check import _sha
from .recording_to_v5 import digest

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
ACQUISITION = SCREEN / "acquisition-support"
OUT = ACQUISITION / "control-parity"
ARCHIVES = (
    (SCREEN / "detector-origins/whole-band", whole_band_results.METHOD["wide"], "wide"),
    (ACQUISITION / "fresh-waveform", fresh_waveform.METHOD, None),
)
NATIVE_FIELDS = ("raw_authority", "clock_sha256", "excluded_sha256", "probes_sha256")
INPUT_FIELDS = ("catalog_sha256", "original_request_sha256", "tile", "mode")


def read(path):
    return json.loads(path.read_bytes())


def bare(value):
    return value.removeprefix("sha256:")


def sealed(folder):
    # This is the first read of any primary study. No prediction is opened
    # until its publication lock exists and binds each artifact's bytes.
    path = folder / "prediction-lock.json"
    if not path.is_file():
        raise FileNotFoundError(f"{folder.name} public prediction lock is pending")
    pin = read(path)
    for filename, checksum in pin["files"].items():
        member = Path(filename)
        if member.is_absolute() or ".." in member.parts or _sha(folder / member) != bare(checksum):
            raise ValueError(f"{folder.name} has an unauthenticated {filename}")
    if not {"source-lock.json", "positions.jsonl.gz", "resources.json"} <= pin["files"].keys():
        raise ValueError("a prediction lock must bind source, positions and resource receipts")
    if len(pin["cases"]) != len(set(pin["cases"])):
        raise ValueError("the sealed roster contains duplicate IDs")
    return pin, _sha(path)


def positions(folder, pin, method):
    with gzip.open(folder / "positions.jsonl.gz", "rt") as stream:
        rows = [r for r in map(json.loads, stream) if r["method"] == method]
    if len(rows) != len(pin["cases"]) or {r["id"] for r in rows} != set(pin["cases"]):
        raise ValueError(f"{folder.name} lacks exact sealed coverage for {method}")
    return {r["id"]: r for r in rows}


def native_signature(payload, expected, receipts):
    if sha256(payload).hexdigest() != bare(expected):
        raise ValueError("native bytes differ from the sealed native SHA-256")
    evidence = json.loads(payload)
    source, provenance = evidence["source"], evidence["provenance"]
    probes = source["probes"]
    excluded = provenance["excluded_windows"]
    clocks = [evidence[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")]
    facts = dict(
        raw_authority=source["raw_recording_authority_digest"],
        input_manifest_sha256=source["input_manifest_sha256"],
        detector_sha256=bare(provenance["detector_sha256"]),
        clock_sha256=digest(clocks),
        excluded_sha256=digest(excluded),
        probes_sha256=digest([{k: v for k, v in p.items() if k != "candidates"} for p in probes]),
        probe_order_sha256=digest(
            [[p["visit_index"], p["receiver_id"], p["probe_index"]] for p in probes]
        ),
        full_probes_sha256=digest(probes),
        probes=len(probes),
        excluded=len(excluded),
        native_sha256=bare(expected),
    )
    for report in receipts:
        for k in (*NATIVE_FIELDS, "input_manifest_sha256", "detector_sha256"):
            if k in report and bare(report[k]) != bare(facts[k]):
                raise ValueError(f"raw receipt disagrees with actual bytes for {k}")
    return facts


def endpoints(control, prior):
    arms = {}
    for arm in ARMS:
        a = coordinate(control["arms"][arm]["latlon"])
        b = coordinate(prior["arms"][arm]["latlon"])
        if a is None or b is None:
            state = (
                "missing_both"
                if a is None and b is None
                else "missing_control"
                if a is None
                else "missing_archive"
            )
            arms[arm] = dict(state=state, exact=None, displacement_km=None)
        else:
            equal = struct.pack("!dd", *a) == struct.pack("!dd", *b)
            arms[arm] = dict(state="compared", exact=equal, displacement_km=distance_km(a, b))
    return dict(control_status=control["status"], archive_status=prior["status"], arms=arms)


def archived(folder, method, branch):
    pin, checksum = sealed(folder)
    resources = read(folder / "resources.json")
    rows = positions(folder, pin, method)
    result = {}
    for ident, row in rows.items():
        receipt = resources[ident] if branch is None else resources[ident][branch]
        member = f"native/{ident}.json.gz"
        signature = None
        if row.get("native_sha256") is not None:
            if member not in pin["files"]:
                raise ValueError("archived complete native factors lack their public digest")
            signature = native_signature(
                gzip.decompress((folder / member).read_bytes()),
                row["native_sha256"],
                [receipt],
            )
        result[ident] = dict(row=row, native=signature, study=folder.name, lock_sha256=checksum)
    return result


def control_signature(folder, pin, scratch, row, resource):
    member = f"native/control/{row['id']}.json.gz"
    native = scratch / "recording/native.json"
    raw = scratch / "raw.json"
    expected = row.get("native_sha256")
    if expected is None:
        # A partial raw attempt cannot be promoted by an unsealed scratch artifact.
        return None, dict(published_native=False, scratch_rechecked=False)
    receipts = [resource]
    if raw.is_file():
        receipt = read(raw)
        if bare(receipt["native_sha256"]) != bare(expected):
            raise ValueError("measured raw receipt differs from the public control")
        receipts.append(receipt)
    if member in pin["files"]:
        payload = gzip.decompress((folder / member).read_bytes())
        if native.is_file() and _sha(native) != bare(expected):
            raise ValueError("measured raw native file differs from the public control")
    elif native.is_file():
        payload = native.read_bytes()
    else:
        return None, dict(published_native=False, scratch_rechecked=False, sealed_digest=expected)
    facts = native_signature(payload, expected, receipts)
    return facts, dict(published_native=member in pin["files"], scratch_rechecked=native.is_file())


def audit(folder, work, recovery=None):
    pin, checksum = sealed(folder)
    source = read(folder / "source-lock.json")
    resources = read(folder / "resources.json")
    spec = source["spec"]
    if set(pin["cases"]) != set(source["cases"]) or set(pin["cases"]) != set(resources):
        raise ValueError("public results and prospective primary roster differ")
    controls = positions(folder, pin, spec["id"] + "_control")
    previous = {}
    for archive_folder, name, branch in ARCHIVES:
        panel = archived(archive_folder, name, branch)
        if previous.keys() & panel.keys():
            raise ValueError("archived reference panels contain ambiguous control matches")
        previous.update(panel)
    results = []
    for ident in pin["cases"]:
        row = controls[ident]
        old = previous[ident]
        before = old["row"]
        if any(row[k] != before[k] for k in INPUT_FIELDS):
            raise ValueError(f"{ident} does not bind the same causal request and region")
        origin = recovery if ident == "DS26-0014" and recovery is not None else work
        current, proof = control_signature(
            folder,
            pin,
            origin / ident / "control",
            row,
            resources[ident]["control"],
        )
        old_native = old["native"]
        equal = (
            {k: current[k] == old_native[k] for k in old_native}
            if current is not None and old_native is not None
            else None
        )
        results.append(
            dict(
                id=ident,
                study=folder.name,
                archive=old["study"],
                control_lock_sha256=checksum,
                archive_lock_sha256=old["lock_sha256"],
                matching_request=dict((k, row[k]) for k in INPUT_FIELDS),
                native_equal=equal,
                native_check=proof,
                control_native=current,
                archive_native=old_native,
                position=endpoints(row["result"], before["result"]),
                control_reason=row["result"].get("reason"),
            )
        )
    return results


def summary(rows):
    return dict(
        scheduled=len(rows),
        native=Counter(
            "missing"
            if r["native_equal"] is None
            else "exact"
            if all(r["native_equal"].values())
            else "different"
            for r in rows
        ),
        calibration={
            arm: Counter(
                ("exact" if d["exact"] else "different") if d["state"] == "compared" else d["state"]
                for r in rows
                if (d := r["position"]["arms"][arm])
            )
            for arm in ARMS
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, choices=("scout-full", "radius-full"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--recovery", type=Path)
    parser.add_argument("--out", type=local_output, default=OUT)
    args = parser.parse_args()
    source = ACQUISITION / args.study
    rows = audit(source, args.work, args.recovery)
    save_json(
        args.out / f"{args.study}.json",
        dict(
            check_sha256=_sha(Path(__file__)),
            primary=args.study,
            summary=summary(rows),
            records=rows,
        ),
    )


if __name__ == "__main__":
    main()
