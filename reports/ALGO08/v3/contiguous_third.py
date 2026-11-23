"""Replay the first third of signed stereo visits and publish normal saved evidence."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from types import SimpleNamespace

from aperture_trial import ARMS, BENCH, DENSE, PAYLOAD, RELEASE, archive_identity, inputs, machine, read, write
from tools.pipeline_eval.variants.capture_bursts import inventories, select_document


HERE = Path(__file__).resolve().parent
CASES = ("DS30-0008", "south-containing", "south-far")
MODES = ("stock", "signed-full", "signed-third")


def native_signature(source, detector, probes):
    from leo.contracts.digests import canonical_digest

    return canonical_digest(["cancellation", source["raw_recording_authority_digest"],
                             detector.removeprefix("sha256:"), probes])


def project(native):
    from leo.contracts.digests import canonical_digest

    source, provenance = native["source"], native["provenance"]
    probes = source["probes"]
    visits = inventories(native)
    count = provenance["window_count"]
    cut = count // 3
    detector = provenance["detector_sha256"]
    if (cut < 1 or provenance["invalid_capture"] != len(provenance["excluded_windows"])
            or provenance["scope"] != "cancellation" or source["sample_rate_hz"] != 10_000_000
            or native_signature(source, detector, probes) != source["analysis_manifest_sha256"]):
        raise ValueError("Expected complete archived v3 receiver provenance")
    admitted = [visit for visit, _ in visits if visit < cut]
    projected = select_document(native, admitted, source["analysis_manifest_sha256"])
    rows = projected["source"]["probes"]
    digest = native_signature(source, detector, rows)
    if digest == source["analysis_manifest_sha256"]:
        raise ValueError("The prefix never removed any later measured candidates")
    projected["source"]["analysis_manifest_sha256"] = digest
    projected["provenance"]["run_id"] = "blind-compact-" + digest[7:39]
    prefix_rows = [r for r in rows if r["visit_index"] < cut]
    return projected, dict(
        recorded_visits=count, prefix_visits=cut, admitted_prefix_stereo=len(admitted),
        admitted_full_stereo=len(visits), skipped_valid_stereo=len(visits) - len(admitted),
        prefix_channels=dict(sorted(Counter(channel for visit, channel in visits if visit < cut).items())),
        estimated_prefix_detector_call_fraction=len(admitted) / len(visits),
        full_candidates=sum(len(r["candidates"]) for r in probes),
        retained_candidates=sum(len(r["candidates"]) for r in prefix_rows),
        prefix_exact_rows_sha256=canonical_digest(prefix_rows),
        last_prefix_delivery_s=(native["delivery_clocks"][cut - 1]["monotonic_ns"]
                                - native["clock_anchor"]["before"]["monotonic_ns"]) / 1e9,
        full_delivery_s=(native["delivery_clocks"][-1]["monotonic_ns"]
                         - native["clock_anchor"]["before"]["monotonic_ns"]) / 1e9,
        analysis_manifest_sha256=digest,
    )


def observe_prepared(prepared):
    tracks = prepared["tracks"]
    meta = tracks["metadata"]
    cutoff = meta["causal_cutoff_utc_ns"]
    times = [row["time_s"] for row in tracks["observations"]]
    audit = dict(status=prepared["status"], origin_utc_ns=meta["anchor_utc_ns"], cutoff_utc_ns=cutoff,
                 duration_s=meta["duration_s"], observations=len(times), last_observation_s=max(times, default=None),
                 tracks=len(tracks["tracks"]), last_track_s=max((t["end_s"] for t in tracks["tracks"]), default=None),
                 receiver_factors=meta["receiver_factors"], empty_factors=meta["empty_factors"])
    if prepared["sky"] is not None:
        sky, history = prepared["sky"], prepared["phase_history"]
        catalogue = [row["provenance"] for row in sky["nominal_elements"].values()]
        authorities = [max(row["collected_utc_ns"], row["element_epoch_utc_ns"]) for row in catalogue]
        forecasts = [row["validation_time_ns"] for row in prepared["phase_forecast"]["transitions"]]
        latest = max([*authorities, *forecasts, *(row["collected_utc_ns"] for row in history["sources"])],
                     default=None)
        if sky["metadata"]["cutoff_utc_ns"] != cutoff or history["cutoff_utc_ns"] != cutoff or (
                latest is not None and latest > cutoff):
            raise ValueError("The inference consumed post-origin orbit evidence")
        audit.update(catalogue_candidates=len(catalogue), phase_transitions=len(forecasts),
                     latest_orbit_evidence_utc_ns=latest)
    return audit


def calibration_owners(raw, selected):
    source = raw["source"]
    available = {"sha256:" + sha256(f"{source['session_id']}:{r['receiver_id']}:{r['valid_start_counter']}".encode()).hexdigest()
                 for r in source["probes"] if any(c["passed_fractional_margin_gate"] for c in r["candidates"])}
    for arm in ARMS:
        keys = [r[0] for r in selected.get(arm, [])]
        if len(set(keys)) != len(keys) or not set(keys) <= available:
            raise ValueError(f"{arm} output claimed an observation outside the admitted receiver factors")


def run(case, output):
    from leo.contracts.digests import canonical_digest
    from signed_0374_transfer import owner_changes
    from tools.pipeline_eval.qualification.paired_publication import evidence

    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(n != "1" for n in system["threads"].values())):
        raise ValueError("Use the shared Gauss lock and one low-priority numerical core")
    original, archive, offer, expected, identity = inputs(case)
    prefix, audit = project(original)
    output.mkdir(exist_ok=False)
    offer_path = output / "offer.json"
    write(offer_path, offer)
    full_path, prefix_path = output / "full.json", output / "third.json"
    write(full_path, original)
    write(prefix_path, prefix)
    pair = read(DENSE if case == "DS30-0008" else BENCH / "exact-curved-lookahead-south-inside/pair.json")
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE))),
                       MPLCONFIGDIR=str(output / "mplconfig"))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        environment.pop(key, None)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=environment, check=True, timeout=20)
    runs = {}
    selected = {}
    for mode, raw, input_path in zip(MODES, (original, original, prefix), (full_path, full_path, prefix_path), strict=True):
        root = output / mode
        digest = canonical_digest(raw)
        args = [python, "-BPs", str(Path(__file__).resolve()), "publish", pair["recording"], str(archive),
                str(offer_path), str(root), str(input_path), digest, mode]
        began = perf_counter()
        child = subprocess.run(args, env=environment, capture_output=True, text=True, timeout=140)
        if child.returncode:
            write(output / f"{mode}-failure.json", dict(elapsed_s=perf_counter() - began, stderr=child.stderr))
            raise RuntimeError(f"{case} {mode} exited {child.returncode}: {child.stderr[-3000:]}")
        receipt_path = root / "joint-research-receipt.json"
        result = read(receipt_path)
        science = evidence(root, result["receipt"], 0, read_only=True)
        if (result["saved_digest"] != digest or result["saved_handoff_manifest"] != raw["source"]["input_manifest_sha256"]
                or science["raw_authority"] != identity["raw_authority"] or science["receipt"]["region"] != offer):
            raise ValueError("The reported outputs changed saved input or offer")
        if science["receipt"]["decision"] == "complete" and not result["solve"]["grid_complete"]:
            raise ValueError("A numerical return failed full evidence")
        selected[mode] = result["selected_rows"]
        calibration_owners(raw, selected[mode])
        runs[mode] = dict(science, **{key: result[key] for key in ("solve", "route", "route_details", "selected_roles",
                           "source_sha256", "publication_cpu_s", "publication_elapsed_s")},
                          observer_sha256=sha256(receipt_path.read_bytes()).hexdigest(), native_sha256=digest)
        if mode == "stock":
            fields = dict(arms=science["arms"], reason=science["reason"],
                          status="ok" if science["receipt"]["decision"] == "complete" else "withheld",
                          owners=science["owners"], science=science["scientific_digests"],
                          orbit_policy=result["solve"]["orbit_policy"])
            for key, value in fields.items():
                archived = (expected.get(key) or {}) if key == "owners" else expected[key]
                if value != archived:
                    raise ValueError(f"Fresh stock output changed archived {key}")
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Capture-era archive changed during the case")
    overlap = {mode: {base: owner_changes(dict(selected_rows=selected[base]), dict(selected_rows=selected[mode]))
                      for base in MODES if base != mode} for mode in MODES if mode != "stock"}
    write(output / "sealed.json", dict(case=case, identity=identity, machine=system, mask=audit,
                                       driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                                       runs=runs, overlap=overlap))


def score(directory, receipt, summary):
    from aperture_score import PHYSICAL, SIMULATED, distance_km, references

    paths = {case: directory / case / "sealed.json" for case in CASES}
    sealed = {case: read(path) for case, path in paths.items()}
    for case, row in sealed.items():
        for mode, record in row["runs"].items():
            observer = directory / case / mode / "joint-research-receipt.json"
            if sha256(observer.read_bytes()).hexdigest() != record["observer_sha256"]:
                raise ValueError("A run observer changed after sealing")
    truth = references()
    numbers = {}
    for case, row in sealed.items():
        out = {}
        for mode, record in row["runs"].items():
            detail = record["route_details"] or {}
            stages = {key: value for key, value in detail.items() if key.endswith("_clocks")}
            signed = detail.get("signed", {})
            arms = record["arms"]
            out[mode] = dict(
                decision=record["receipt"]["decision"], reason=record["reason"], route=record["route"],
                route_reason=detail.get("reason"), signed_status=signed.get("status"), stages=stages,
                horizontal_error_km={arm: distance_km(arms[arm]["latlon"], truth[case])
                                     if arms[arm]["latlon"] is not None else None for arm in ARMS},
                rf_rms_hz={arm: arms[arm].get("rf_rms_hz") for arm in ARMS},
                **{key: record[key] for key in ("solve", "publication_cpu_s", "publication_elapsed_s", "selected_roles")},
            )
        third = out["signed-third"]
        deltas = {mode: {arm: third["horizontal_error_km"][arm] - out[mode]["horizontal_error_km"][arm]
                         if third["horizontal_error_km"][arm] is not None and out[mode]["horizontal_error_km"][arm] is not None
                         else None for arm in ARMS} for mode in MODES[:2]}
        passes = third["decision"] == "withheld" if case.endswith("far") else (
            third["decision"] == "complete" and all(delta is not None and delta <= .25
                                                     for arms in deltas.values() for delta in arms.values()))
        numbers[case] = dict(modes=out, mask=row["mask"], overlap=row["overlap"], delta_error_km=deltas, triage_pass=passes)
    pins = dict(seals={case: sha256(path.read_bytes()).hexdigest() for case, path in paths.items()},
                references={path.name: sha256(path.read_bytes()).hexdigest() for path in (PHYSICAL, SIMULATED)})
    write(summary, dict(cases=numbers, verification=pins))
    with receipt.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(cases=sealed, scores=numbers, verification=pins), sort_keys=True,
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


def publish(recording, archive, region, output, saved, digest, mode):
    from joint_publication import run

    run(SimpleNamespace(recording=recording, archive=archive, region=region, output=output, saved=saved,
                        saved_digest=digest, verify_images=True, stock_control=mode == "stock",
                        signed_finish=mode != "stock", observe_prepared=observe_prepared))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    timing = actions.add_parser("run")
    timing.add_argument("case", choices=CASES)
    timing.add_argument("output", type=Path)
    scoring = actions.add_parser("score")
    for name in ("directory", "receipt", "summary"):
        scoring.add_argument(name, type=Path)
    child = actions.add_parser("publish")
    for name in ("recording", "archive", "region", "output", "saved"):
        child.add_argument(name, type=Path)
    child.add_argument("digest")
    child.add_argument("mode", choices=MODES)
    options = vars(parser.parse_args())
    action = options.pop("action")
    {"run": run, "score": score, "publish": publish}[action](**options)


if __name__ == "__main__":
    main()
