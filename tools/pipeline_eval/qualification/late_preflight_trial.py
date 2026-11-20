"""Replay an RF-only reassociation gate on the original causal cavity evidence."""

import argparse
import io
import json
from pathlib import Path
from time import perf_counter, process_time
from zipfile import ZipFile

from ..__main__ import local_output, save_json
from ..scoring import ARMS
from ..variants import late_preflight as guard
from ..variants.v5_lean import SOURCE_SHA256
from . import full_receiver_comparison as authority
from . import pruned_finish_audit as archive_reader
from .short_receiver_figures import _frozen_roof
from .v5_postfit import _map, sha256
from .v5_prefix_audit import value

REPORT = authority.SCREEN / "recovery/late-preflight"
PRIOR = authority.SCREEN / "inference/pruned-finish/audit/eligibility.json"
METHOD = "late_preflight_archive"
CONTROL = "late_preflight_cavity_archive"
DIAGNOSTIC = ("DS26-0066", "DS26-0287")
STAGES = ("ranking", "admission", "final")
MATCH = ["native_sha256", "catalog_sha256", "tile"]


def local_field(raw, start):
    decoder = json.JSONDecoder()
    size = 4096
    while True:
        try:
            return decoder.raw_decode(raw[start : start + size].decode("utf-8", "ignore"))[0][1]
        except json.JSONDecodeError:
            if size >= len(raw) - start:
                raise
            size *= 2


def cavity_arms(raw):
    key = b'["cavity_policy",["map",'
    if raw.count(key) != 1:
        raise ValueError("expected one complete cavity evidence object")
    start = raw.index(key)
    policy = raw.index(b'["policy_arms",', start)
    if policy > raw.index(b'["recovery_inventory",', start):
        raise ValueError("cavity arms escaped their original checkpoint")
    return _map(local_field(raw, policy))


def archived_rf(cavity, archive):
    return {
        arm: [
            (
                t["norad"],
                t["component"],
                t["points"],
                value(t["profile_bias_hz"], archive),
                value(_map(t["conditional_residual_gate"])["rms_hz"], archive),
            )
            for t in archive_reader._rows(_map(_map(cavity[arm])["gates"])["tracks"])
            if t["compatible"]
        ]
        for arm in ARMS
    }


def timing(feature):
    cpu = process_time()
    wall = perf_counter()
    go, reason, families = guard.preflight(feature)
    return dict(
        run=go,
        reason=reason,
        plausible=families,
        cpu_s=process_time() - cpu,
        wall_s=perf_counter() - wall,
    )


def axes(arms, archive, *, is_final=False):
    out = {}
    for arm in ARMS:
        row = _map(arms[arm])
        key = "x" if is_final else "endpoint_east_north_km"
        out[arm] = dict(x=value(row[key], archive), axis_sha256=row[key][1])
    return out


def incumbent_and_outcome(raw, archive, worker, cavity, eligibility):
    handoff = b'["reassociation_handoff",["map",[["arms",'
    offset = raw.index(handoff) + handoff.index(b'["arms",')
    incumbent = _map(local_field(raw, offset))
    final = _map(
        archive_reader._checkpoint(raw, "reassociation_complete", "reassociation_evaluated")[
            "recovery"
        ]
    )
    if final["execution_status"] != "complete":
        raise ValueError("expected complete stock final checkpoint")
    baseline_axes = axes(_map(final["baseline"]), archive, is_final=True)
    if baseline_axes != axes(incumbent, archive):
        raise ValueError("late baseline changed away from original post-addition handoff")
    final_axes = axes(_map(final["final"]), archive, is_final=True)
    updates = dict(
        selected=final["selected"],
        targets=final["targets"][1],
        control_fits=final["control_fits"],
        candidate_fits=final["candidate_fits"],
    )
    stages = {}
    for arm in ARMS:
        stock = worker["arms"][arm]
        start, post = _map(cavity[arm]), _map(incumbent[arm])
        stages[arm] = dict(
            cavity=dict(
                latlon=value(start["endpoint_latlon"], archive),
                x=value(start["endpoint_east_north_km"], archive),
                rf_rms_hz=value(start["RMS_hz"], archive),
            ),
            incumbent=dict(
                latlon=value(post["endpoint_latlon"], archive),
                rf_rms_hz=value(post.get("RMS_hz"), archive),
                **baseline_axes[arm],
            ),
            final=dict(
                latlon=stock["endpoint_latlon"],
                rf_rms_hz=stock["residual_rms_hz"],
                **final_axes[arm],
            ),
        )
        if final["selected"] is None and baseline_axes[arm] != final_axes[arm]:
            raise ValueError("no-selection fallback changed its incumbent axes")
        if (
            final["selected"] is None
            and stages[arm]["incumbent"]["latlon"] != stock["endpoint_latlon"]
        ):
            raise ValueError("no-selection endpoint changed its incumbent coordinates")
    times = {record["stage"]: record["seconds"] for record in worker["stage_timings"]}
    return dict(
        stages=stages,
        decision=updates,
        stage_wall_s={k: times[k] for k in STAGES},
        original_eligibility=eligibility,
    )


def extract(ident, entry, binding, eligibility):
    root = archive_reader.DS29 if ident.startswith("DS29-") else archive_reader.ARCHIVE
    folder = root / f"{ident}-r0"
    receipt_bytes = (folder / "baseline-execution.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    archive_bytes = (folder / "baseline/experimental-evidence.zip").read_bytes()
    worker = receipt["worker"]
    request = binding["request_sha256"]
    evidence = worker["artifact"]["sha256"]
    if (
        binding["execution_sha256"].removeprefix("sha256:") != sha256(receipt_bytes)[7:]
        or not receipt["status"] == "complete"
        or receipt["role"] != "baseline"
        or receipt["request_sha256"] != request
        or worker["request_sha256"] != request
        or worker["source_sha256"] != SOURCE_SHA256
        or evidence != sha256(archive_bytes)
        or evidence != eligibility["archive_sha256"]
        or eligibility["archive_receipt_sha256"] != sha256(receipt_bytes)
        or eligibility["request_sha256"] != request
    ):
        raise ValueError(f"{ident} original ZIP, request, execution or eligibility did not match")
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        raw = archive.read("values.json")
        if archive_reader._field(raw, "request_sha256") != request:
            raise ValueError(f"{ident} evidence has a different original request")
        cavity = cavity_arms(raw)
        features = archived_rf(cavity, archive)
        prediction = timing(features)
        outcome = incumbent_and_outcome(raw, archive, worker, cavity, eligibility)
    return dict(
        id=ident,
        archive_sha256=evidence,
        execution_sha256=binding["execution_sha256"],
        request_sha256=request,
        native_sha256=entry["native"]["sha256"],
        catalog_sha256=entry["catalog"]["sha256"],
        tile=entry["regions"][0],
        features=features,
        preflight=prediction,
    ), outcome


def collect(output):
    refs, inventory = _frozen_roof()
    inputs = authority.full_roster(refs, inventory)
    originals_path = authority.secant_full.REPORT / "original-v5-inputs.json"
    authority.seal(originals_path.parent, "receipt.json", (originals_path.name,))
    originals = authority.read(originals_path)
    eligible = {r["id"]: r for r in authority.read(PRIOR)["rows"]}
    authority.roster_matches(eligible, inputs, "pre-existing exact late eligibility")
    authority.roster_matches(originals, inputs, "original baseline execution seal")
    blind, labels = [], []
    for ident, entry in inputs.items():
        row, outcome = extract(ident, entry, originals[ident]["baseline"], eligible[ident])
        blind.append(row)
        labels.append(dict(id=ident, **outcome))
        print(ident, flush=True)
    save_json(output / "predecision.json", blind)
    files = {"predecision.json": authority.sha(output / "predecision.json")}
    save_json(
        output / "predecision-lock.json",
        dict(
            cases=sorted(inputs),
            files=files,
            original_v5_inputs_sha256=authority.sha(originals_path),
            original_v5_run_receipt_sha256=authority.sha(originals_path.parent / "receipt.json"),
            prior_eligibility_sha256=authority.sha(PRIOR),
            source_sha256={
                str(path.relative_to(authority.ROOT)): authority.sha(path)
                for path in (Path(__file__), Path(guard.__file__), REPORT / "PROTOCOL.md")
            },
        ),
    )
    save_json(output / "outcomes.json", labels)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT)
    collect(local_output(parser.parse_args().output))
