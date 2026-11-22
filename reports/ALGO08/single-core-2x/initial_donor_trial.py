"""Compare initial-lane donor measurements with the frozen conditional receiver."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastSegmentSource
from residual_native_trial import ScheduledReceiver, candidates
from residual_schedule_trial import read as read_ledger
from selected_changes import bound_native, changes
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification.full_v5_check import _probe
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.initial_donors import InitialDonors
from tools.pipeline_eval.variants.experimental.residual_schedule import Replay


def lane(row):
    return row["receiver_id"], row["channel"], row["actual_rf_hz"]


def prefix_limit(rows):
    visits = defaultdict(list)
    for r in rows:
        if len(visits[lane(r)]) < 15:
            visits[lane(r)].append(r["visit_index"])
    if not visits or any(len(v) != 15 for v in visits.values()):
        raise ValueError("Every lane must reach fifteen visits for this bounded trial")
    return 1 + max(v[-1] for v in visits.values())


class Comparison:
    def __init__(self):
        self.planners = Replay("conditional"), InitialDonors()
        self.deltas = {}
        self.extra = []

    def visit(self, meta, measure, published=None):
        results = [policy.visit(meta, measure) for policy in self.planners]
        (standard, _, original), (initialized, _, updated) = results
        if published is not None and dict(meta, candidates=original) != published:
            raise ValueError("Conditional control disagrees with the published row")
        key = meta["visit_index"], meta["receiver_id"]
        if standard != initialized:
            if standard or not initialized:
                raise ValueError("Unexpected scan mode change")
            self.extra.append(key)
        if original != updated:
            self.deltas[key] = updated
        return original, updated

    def check_join(self):
        left, right = self.planners
        if not (left.opportunities == right.opportunities and left.last_residual == right.last_residual
                and left.continuation.by_lane == right.continuation.by_lane
                and min(left.opportunities.values()) >= 15):
            raise ValueError("Receiver state did not converge on every lane")


def ledger(path, saved, expected):
    digest, data, native = read_ledger(path, saved)
    rows = data["rows"]
    trial = Comparison()
    ctrl, init = [], []
    for row in rows:
        factors = row["candidates"]
        before, after = trial.visit(row, lambda full: factors if full else [f for f in factors if f["candidate_rank"] == 0])
        ctrl.append(dict(row, candidates=before))
        init.append(dict(row, candidates=after))
    trial.check_join()
    if digest != expected["ledger_sha256"] or canonical_digest(ctrl) != expected["arms"]["conditional"]["selected_sha256"]:
        raise ValueError("Ledger or conditional replay differs from the previous benchmark")
    reference = native["source"]["probes"]
    return dict(ledger_sha256=digest, lanes=len(set(map(lane, rows))), extra_full=len(trial.extra),
                rows=len(rows), changed=changes(ctrl, init), remaining_vs_full=changes(reference, init)["changed"])


def raw(pair_path, assets, output):
    pair = json.loads(pair_path.read_bytes())
    run = pair["runs"]["candidate"]
    root = pair_path.parent/"candidate"
    doc = bound_native(root, run)
    source = doc["source"]
    rows = source["probes"]
    detector_sha = doc["provenance"]["detector_sha256"].removeprefix("sha256:")
    raw_id = source["raw_recording_authority_digest"]
    def identity(values):
        return canonical_digest(["cancellation", raw_id, detector_sha, values])
    if identity(rows) != source["analysis_manifest_sha256"]:
        raise ValueError("Conditional analysis binding changed")
    limit = prefix_limit(rows)
    spec = pair["candidate_specification"]
    inventory = json.loads((root/"fast-scan-inputs"/(source["session_id"]+".json")).read_bytes())
    if (spec["schedule"] != "conditional-residual" or canonical_digest(inventory) != source["input_manifest_sha256"]
            or limit > 256 or limit > inventory["segments"][0]["windows"]):
        raise ValueError("Expected a short prefix of one sealed segment under the conditional schedule")
    segment = FastSegmentSource(inventory["segments"][0], stop_sequence=limit)
    edge, = {r["edge"] for r in rows}
    pilot = assets/(edge+".f32")
    binary = Path(spec["detector"])
    if (sha256(pilot.read_bytes()).hexdigest() != PINS[pilot.name]
            or sha256(binary.read_bytes()).hexdigest() != detector_sha
            or spec["detector_sha256"] != detector_sha or tuple(segment.receiver_ids) != (0, 1)):
        raise ValueError("Unexpected pilot, receiver or antenna order")
    expected = {(r["visit_index"], r["receiver_id"]): r for r in rows if r["visit_index"] < limit}
    exclusions = {r["visit"]: r["iq_sha256"] for r in doc["provenance"]["excluded_windows"]}
    trial = Comparison()
    checked = set()
    extra_times = Counter()
    policy = FastScanPolicyV2()
    asset = np.fromfile(pilot, dtype="<f4")
    with closing(ScheduledReceiver(binary, asset)) as radio, compressed_input_buffer():
        for index, window in enumerate(segment.windows()):
            acq, target, samples = window.acquisition, window.target, window.samples
            if index != acq["global_visit"] or window.sample_rate_hz != 10_000_000:
                raise ValueError("Unexpected visit order or sample rate")
            if not valid_window_support(acq, window.sample_rate_hz, samples.shape, (0, 1), policy):
                if exclusions.get(index) != window.iq_sha256:
                    raise ValueError("Unexpected excluded window")
                continue
            center = target["rf_center_hz"]-target["lnb_lo_hz"]-acq["actual_if_center_hz"]
            if (samples.shape != (200000, 2, 2) or samples.dtype != np.dtype("<i2")
                    or not samples.flags.c_contiguous or edge != target["edge"] or abs(center) > 4_200_000):
                raise ValueError("Unexpected raw window layout")
            for antenna in (0, 1):
                meta = _probe(window, antenna, [])
                key = index, antenna
                measured, clock = {}, {}
                def measure(full):
                    if full not in measured:
                        run_native = radio.timed if full else radio.timed_primary
                        factors, clock[full], _ = run_native(samples, antenna, center)
                        measured[full] = candidates(factors)
                    return measured[full]
                trial.visit(meta, measure, expected[key])
                if len(clock) == 2:
                    if measured[False] != [f for f in measured[True] if f["candidate_rank"] == 0]:
                        raise ValueError("Changing scan mode changed the verified primary")
                    extra_times.update({"primary_cpu_ns": clock[False], "full_cpu_ns": clock[True]})
                checked.add(key)
    if checked != expected.keys():
        raise ValueError("Missing paired prefix opportunities")
    trial.check_join()
    updated = [dict(r, candidates=trial.deltas.get((r["visit_index"], r["receiver_id"]), r["candidates"]))
               for r in rows]
    digest = identity(updated)
    altered = dict(doc, source=dict(source, probes=updated, analysis_manifest_sha256=digest),
                   provenance=dict(doc["provenance"], run_id="blind-compact-"+digest[7:39]))
    with output.open("x") as stream:
        json.dump(altered, stream, allow_nan=False)
    return dict(raw_authority=raw_id, pair_sha256=sha256(pair_path.read_bytes()).hexdigest(),
                detector_sha256=detector_sha, prefix_visits=limit, admitted_prefix_lanes=len(checked),
                extra_full=len(trial.extra), added_calls_cpu=extra_times, input_digest=digest,
                changed=changes(rows, updated), join_opportunities=sorted(trial.planners[0].opportunities.values()))


def position(pair_path, prefix_path, native_path, frozen, request_path, output):
    from leo.contracts.algo08_region import Algo08Region
    from residual_attribution_trial import RELEASE, read, write
    from tools.pipeline_eval.qualification.paired_publication import archive_identity, verify_sources

    prefix, pair, native = (read(p) for p in (prefix_path, pair_path, native_path))
    src = native["source"]
    spec = read(frozen/"spec.json")
    archive = request_path.parent/"tle"
    offer = Algo08Region.parse(read(Path(pair["region"]))).document()
    native_id = canonical_digest(["cancellation", src["raw_recording_authority_digest"],
                                  prefix["detector_sha256"], src["probes"]])
    if (prefix["pair_sha256"] != sha256(pair_path.read_bytes()).hexdigest()
            or spec != pair["candidate_specification"] or canonical_digest(spec) != pair["candidate_specification_digest"]
            or spec["detector_sha256"] != prefix["detector_sha256"]
            or src["analysis_manifest_sha256"] != native_id or native_id != prefix["input_digest"]
            or src["raw_recording_authority_digest"] != pair["runs"]["candidate"]["raw_authority"]
            or any(r["receipt"]["region"] != offer for r in pair["runs"].values())
            or pair["archive"]["snapshots_sha256"] != canonical_digest(read(request_path)["causal_snapshots"])
            or archive_identity(archive) != pair["archive"]):
        raise ValueError("Solver inputs differ from the frozen matched recording")
    verify_sources(frozen/"reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    env = {k: v for k, v in os.environ.items() if not k.startswith("ALGO08_")}
    env.update(PYTHONPATH=f"{frozen}:{RELEASE/'src'}:{RELEASE}", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    worker = Path(__file__).with_name("residual_attribution_trial.py")
    with TemporaryDirectory() as directory:
        region = Path(directory)/"region.json"
        write(region, offer)
        solved = Path(directory)/"solved.json"
        subprocess.run([str(RELEASE/"venv/bin/python"), "-BPs", str(worker), "worker", str(native_path),
                        str(frozen/"spec.json"), str(archive), str(region), str(solved)],
                       env=env, check=True, timeout=240)
        result = read(solved)
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Archive changed during the position run")
    write(output, dict(solver=result, specification_digest=pair["candidate_specification_digest"],
                       archive=pair["archive"], offer=offer, analysis_manifest_sha256=native_id))
    return result


def score_case(solved_path, prefix_path, controls_path, reference_path):
    from residual_attribution_trial import ARMS, CASE, REFERENCE_SHA256, read
    from tools.pipeline_eval.scoring import distance_km

    result, prefix, controls = (read(p) for p in (solved_path, prefix_path, controls_path))
    if (result["analysis_manifest_sha256"] != prefix["input_digest"]
            or prefix["pair_sha256"] != controls["plan"]["pair_sha256"]
            or result["specification_digest"] != controls["plan"]["specification_digest"]
            or result["archive"] != controls["plan"]["archive"] or result["offer"] != controls["plan"]["region"]
            or controls["verified_controls"] != {"unchanged": "candidate", "restore-all": "baseline"}
            or sha256(reference_path.read_bytes()).hexdigest() != REFERENCE_SHA256):
        raise ValueError("Scoring inputs differ from the locked fit and verified controls")
    reference, = [case["reference"] for case in read(reference_path)["cases"]
                  if case["dataset_label"] == CASE and case["authority_eligible"]]
    point = (reference["latitude_deg"], reference["longitude_deg"])
    fits = {"deployed": controls["results"]["restore-all"], "conditional": controls["results"]["unchanged"],
            "initial_donors": result["solver"]}
    metrics = {name: {arm: dict(error_km=distance_km(fit["arms"][arm]["latlon"], point),
                                 rf_rms_hz=fit["arms"][arm]["rf_rms_hz"],
                                 associated=fit["associated"][arm]) for arm in ARMS} for name, fit in fits.items()}
    return dict(raw_prefix=prefix, solve=result, metrics=metrics, scoring_reference_sha256=REFERENCE_SHA256)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cmds = cli.add_subparsers(dest="action", required=True)
    replay = cmds.add_parser("ledger")
    for field in ("ledger", "saved", "receipt"):
        replay.add_argument(field, type=Path)
    replay.add_argument("case")
    iq = cmds.add_parser("raw")
    for field in ("pair", "assets", "output"):
        iq.add_argument(field, type=Path)
    fit = cmds.add_parser("position")
    for field in ("pair", "prefix", "native", "frozen", "request", "output"):
        fit.add_argument(field, type=Path)
    scoring = cmds.add_parser("score")
    for field in ("solved", "prefix", "controls", "reference"):
        scoring.add_argument(field, type=Path)
    args = cli.parse_args()
    if args.action == "raw":
        result = raw(args.pair, args.assets, args.output)
    elif args.action == "position":
        result = position(args.pair, args.prefix, args.native, args.frozen, args.request, args.output)
    elif args.action == "score":
        result = score_case(args.solved, args.prefix, args.controls, args.reference)
    else:
        result = ledger(args.ledger, args.saved, json.loads(args.receipt.read_bytes())[args.case])
    print(json.dumps(result, indent=2, allow_nan=False))
