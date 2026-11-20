"""Score paired cavity endpoints and authenticate the four original role controls."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution
from ..variants import v5_lean
from . import optional_cavity_trial as trial
from .portable_gate_trials import checksum, compressed_rows
from .v5_postfit import ARCHIVE

OUT = trial.OUT
BINDINGS = ("native_sha256", "catalog_sha256", "track_config_sha256", "frozen_request_sha256")


def original_controls(item, ref):
    folder = ARCHIVE / f"{item['id']}-r0"
    original, snapshots = {}, None
    for role in ROLES:
        request_path = folder / role / "experimental-request.json"
        execution_path = folder / f"{role}-execution.json"
        request = json.loads(request_path.read_bytes())
        record = json.loads(execution_path.read_bytes())
        digest = "sha256:" + sha256(encoded(request)).hexdigest()
        catalogue = request["causal_snapshots"]
        if snapshots is None:
            snapshots = catalogue
        last = max(
            (int(name.split("-")[0]), checksum.removeprefix("sha256:"))
            for name, checksum in catalogue.items()
            if int(name.split("-")[0]) < item["cutoff_utc_ns"]
        )
        job = request["job"]
        assert (
            record["role"] == request["role"] == role
            and record["request_sha256"] == digest
            and request["source"]["sha256"] == v5_lean.SOURCE_SHA256
            and job["evaluation_reference"] is None
            and job["identity"]["session_id"] == item["session_id"]
            and job["search_center"] == item["regions"][0]["center"]
            and job["native_input"]["sha256"] == "sha256:" + item["native"]["sha256"]
            and job["track_config"]["sha256"] == "sha256:" + item["track_config"]["sha256"]
            and last == (item["catalog_timestamp_ns"], item["catalog"]["sha256"])
            and snapshots == catalogue
        )
        if record["status"] == "complete":
            assert record["worker"]["request_sha256"] == digest
        endpoints = ref["reference"].get(role, {})
        original[role] = dict(
            status=record["status"],
            execution_sha256=checksum(execution_path),
            request_sha256=digest,
            arms=endpoints,
        )
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirmed", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    seal = json.loads((OUT / "prediction-lock.json").read_bytes())
    for name, digest in seal["files"].items():
        assert checksum(OUT / name) == digest
    plan = json.loads((OUT / "plan.json").read_bytes())
    original = {r["id"]: r for r in corpus.references("ds26-all159")}
    _, frozen = corpus._selection("ds26-all159")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", frozen))
    pairs = list(
        map(json.loads, gzip.decompress((OUT / "paired.jsonl.gz").read_bytes()).splitlines())
    )
    assert len(pairs) == 2 * len(plan["cases"])
    corrected = {}
    for path in args.confirmed:
        row = json.loads((path / "row.json").read_bytes())
        source = json.loads((path / "source-lock.json").read_bytes())
        key = (row["id"], row["method"])
        first = next(r for r in pairs if (r["id"], r["method"]) == key)
        serialized = json.dumps(first, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
        assert (
            first["result"]["reason"] == "KeyError: 'final_phase_change_s'"
            and row["first_attempt_sha256"] == sha256(serialized).hexdigest()
            and row["corrected_source"] == source
            and source["original"] == plan["source"]
            and key not in corrected
        )
        corrected[key] = row
    confirmed = OUT / "confirmed.jsonl.gz"
    write(confirmed, compressed_rows(corrected.values()))
    pairs = [corrected.get((r["id"], r["method"]), r) for r in pairs]
    write(OUT / "comparison.jsonl.gz", compressed_rows(pairs))
    results, comparisons, controls = [], [], {}
    for query in plan["cases"]:
        ident = query["id"]
        ref = original[ident]
        controls[ident] = original_controls(inputs[ident], ref)
        matching = {r["method"]: r for r in pairs if r["id"] == ident}
        assert matching.keys() == {trial.STOCK, trial.METHOD}
        for row in matching.values():
            assert all(row[k] == query[k] for k in (*BINDINGS, "tile", "condition"))
            result = row["result"]
            for arm in ARMS:
                a = result["arms"][arm]
                results.append(
                    dict(
                        id=ident,
                        condition=query["condition"],
                        method=row["method"],
                        arm=arm,
                        status=result["status"],
                        reason=result.get("reason"),
                        published=a["latlon"] is not None,
                        position_error_km=distance_km(a["latlon"], ref["truth"]),
                        rf_rms_hz=a.get("rf_rms_hz"),
                        wall_s=row["worker_wall_s"],
                        cpu_s=row["cpu_s"],
                        graph_tracks=result["metrics"].get("tracks"),
                        optional_cavity=result["metrics"].get("optional_cavity"),
                    )
                )
        stock, candidate = (matching[m]["result"] for m in (trial.STOCK, trial.METHOD))
        comparisons.append(
            dict(
                id=ident,
                condition=query["condition"],
                stock=stock["status"],
                candidate=candidate["status"],
                same_arms=stock["arms"] == candidate["arms"],
                optional=candidate["metrics"].get("optional_cavity"),
            )
        )
    cohorts = {}
    for condition in ("diagnosed", "control"):
        for method in (trial.STOCK, trial.METHOD):
            for arm in ARMS:
                group = [
                    r
                    for r in results
                    if (r["condition"], r["method"], r["arm"]) == (condition, method, arm)
                ]
                cohorts[f"{condition}/{method}/{arm}"] = dict(
                    attempted=len(group),
                    published=sum(r["published"] for r in group),
                    **{
                        k: distribution(r[k] for r in group)
                        for k in ("position_error_km", "rf_rms_hz", "wall_s", "cpu_s")
                    },
                )
    save_json(OUT / "scores.json", dict(comparisons=comparisons, cohorts=cohorts, outcomes=results))
    save_json(OUT / "original-four.json", controls)
    files = (
        "comparison.jsonl.gz",
        "paired.jsonl.gz",
        "confirmed.jsonl.gz",
        "plan.json",
        "original-four.json",
    )
    save_json(
        OUT / "figure-lock.json",
        dict(
            cases=[r["id"] for r in plan["cases"]],
            files={name: checksum(OUT / name) for name in files},
        ),
    )


if __name__ == "__main__":
    main()
