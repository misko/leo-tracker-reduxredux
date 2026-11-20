"""Measure the position that stopping v5 at an earlier scientific checkpoint would publish."""

import argparse
import gzip
import hashlib
import io
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from ..__main__ import encoded, references, write
from ..scoring import ARMS, distance_km
from ..variants.v5_lean import SOURCE_SHA256
from .v5_postfit import ARCHIVE, _map, sha256

DS29 = Path("/srv/bulk/leo-dev/blind-v5-comparison-20261118/ds29")
STAGES = ("initial", "conservative", "family", "signed", "cavity")


def cohorts():
    common = references("ds26-common127", None)[1]
    ordered = sorted(
        common, key=lambda r: hashlib.sha256(("v5-prefix-dev-1/" + r["id"]).encode()).digest()
    )
    roof29 = [r for r in references("roof16", None)[1] if r["group"] == "DS29"]
    return {"development": ordered[:16], "confirmation": ordered[16:] + roof29}


def value(node, archive):
    if not isinstance(node, list):
        return node
    kind, data, *tail = node
    if kind == "array":
        blob = archive.read(data.removeprefix("sha256:"))
        if sha256(blob) != data:
            raise ValueError("checkpoint array digest mismatch")
        return np.load(io.BytesIO(blob), allow_pickle=False).tolist()
    if kind == "float":
        return float.fromhex(data)
    if kind == "scalar":
        return np.frombuffer(bytes.fromhex(tail[0]), dtype=data).item()
    if kind in ("tuple", "list"):
        return [value(item, archive) for item in data]
    raise ValueError(f"unsupported checkpoint value {kind}")


def checkpoint_rows(tree, archive, center):
    audit = _map(tree["audit"])
    initial = _map(audit["initial"])
    choices = [_map(item) for item in initial["choices"][1]]
    (chosen,) = [c for c in choices if c["hypothesis"] == initial["selected_hypothesis"]]
    stages = {
        "initial": chosen["arms"],
        "conservative": _map(audit["recovery"])["arms"],
        "family": _map(audit["history_policy"])["policy_arms"],
        "signed": _map(audit["signed_policy"])["arms"],
        "cavity": _map(audit["cavity_policy"])["policy_arms"],
        "final": _map(tree["selected"])["arms"],
    }
    results = {}
    for stage, pair in stages.items():
        output = {}
        for arm, record in _map(pair).items():
            row = _map(record)
            if stage == "initial":
                row = _map(row["fit"])
                east, north = value(row["parameters"], archive)
                point = [
                    center[0] + north / 111,
                    center[1] + east / (111.32 * np.cos(np.deg2rad(center[0]))),
                ]
            else:
                if stage == "conservative":
                    row = _map(row["record"])
                point = value(row["endpoint_latlon"], archive)
            if stage == "conservative":
                row = _map(row["fit"])
            rms = row.get("RMS_hz", row.get("rms_hz", row.get("residual_rms_hz")))
            output[arm] = dict(latlon=point, conditional_rms_hz=value(rms, archive))
        if set(output) != set(ARMS):
            raise ValueError(f"unpaired calibration arms at {stage}")
        results[stage] = output
    return results


def audit_case(ref):
    root = ARCHIVE if ref["group"] == "DS26" else DS29
    directory = root / (ref["id"] + "-r0")
    receipt = json.loads((directory / "baseline-execution.json").read_bytes())
    worker = receipt["worker"]
    raw = (directory / "baseline/experimental-evidence.zip").read_bytes()
    if (
        receipt["role"] != "baseline"
        or receipt["status"] != "complete"
        or worker["source_sha256"] != SOURCE_SHA256
        or worker["artifact"]["sha256"] != sha256(raw)
    ):
        raise ValueError(f"{ref['id']} lacks an intact original v5 result")
    with ZipFile(io.BytesIO(raw)) as archive:
        tree = _map(json.loads(archive.read("values.json"))["tree"])
        if tree["request_sha256"] != receipt["request_sha256"]:
            raise ValueError("checkpoint request binding differs from its worker")
        job = _map(_map(tree["request"])["job"])
        center = value(job["search_center"], archive)
        stages = checkpoint_rows(tree, archive, center)
    for arm in ARMS:
        original = ref["reference"]["baseline"][arm]["latlon"]
        distance = distance_km(stages["final"][arm]["latlon"], original)
        if distance is None or distance > 1e-6:
            raise ValueError(f"{ref['id']} calibrated endpoint differs from benchmark")
    times = {s["stage"]: s["seconds"] for s in worker["stage_timings"]}
    return dict(
        id=ref["id"],
        group=ref["group"],
        stages=stages,
        archive_sha256=worker["artifact"]["sha256"],
        stage_s=times,
        original_worker_s=receipt["process"]["wall_seconds"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort", choices=("development", "confirmation"), required=True)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        rows = []
        for row in pool.map(audit_case, cohorts()[args.cohort]):
            rows.append(row)
            print(row["id"], flush=True)
    write(args.out, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))


if __name__ == "__main__":
    main()
