"""One unchanged signed carrier check on the enrolled original rank 68."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch

import moment_preserving_cfo as development


CASE = "DS30-0280"
RANK = 68
CAMPAIGN = development.legacy.FIELD.parent
ROOT = CAMPAIGN / "cases" / CASE
PLAN = "9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
DEVELOPMENT = "6779a1b444a1b0de3e963f4ad60f1c04e309aee0d637e1682c7e4254dcee2c11"
RULE = "f9e0836f40c03a7fa5f20a19a34ac1bcf67f632b830271ef43f0809f3ef8b982"
residual = development.residual


def closed_roles(entry, pair, rows):
    roles = {"installed", "successor"}
    attempts = pair["attempt_result_sha256"]
    if (pair["state"] != "observed_pair" or not pair["chronological"] or not pair["verified_pair"]
            or len(pair["actual_order"]) != 2 or set(pair["actual_order"]) != roles
            or len(rows) != 2 or {row["algorithm"] for row in rows} != roles or set(attempts) != roles):
        raise ValueError("Both original rank-68 roles must verify before the saved readback")
    for row in rows:
        token = attempts[row["algorithm"]]
        if (row["case"] != CASE or row["case_id"] != entry["case_id"] or row["assigned_rank"] != entry["assigned_rank"]
                or row["outcome"] != "complete" or row["acquisition_verified"] is not True
                or row["verified_pair"] is not True or row["attempt_result_sha256"] != token
                or not re.fullmatch("sha256:[0-9a-f]{64}", token)):
            raise ValueError("The completed role does not bind the enrolled attempt")
    return attempts


def run(pair_pin, candidate_seal):
    if os.sched_getaffinity(0) != {3} or any(os.environ.get(name) != "1" for name in (
            "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
            "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")):
        raise ValueError("Require one numerical thread on CPU 3")

    def protect_inputs(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if (path.suffix in (".tle", ".iq", ".sigmf-data") or "fast-scan-recordings" in path.parts
                    or path.is_relative_to("/mnt/qnap01") or "space-track" in path.parts
                    or path.name in ("evaluation-reference.json", "reference-audit.json", "score.json")
                    or path.is_relative_to(CAMPAIGN / "cases") and not path.is_relative_to(ROOT)):
                raise RuntimeError("Only sealed rank-68 signed numerical operands are eligible")

    sys.addaudithook(protect_inputs)
    here = development.HERE
    sealed = residual.read(here / "measurements/moment-preserving-cfo-development.json", DEVELOPMENT)
    if sealed["forward"] != dict(case=CASE, rank=RANK, development_screen_passed=True, opened=False):
        raise ValueError("The frozen development receipt does not authorize this held readback")
    for name, pin in {**development.PINS, "moment_preserving_cfo.py": RULE,
                      "moment-preserving-cfo-protocol.md": development.PROTOCOL}.items():
        residual.checked(here / name, pin)
    for name, pin in {**residual.RELEASE_PINS, "leo/analysis/tracklet_fitting.py":
                      sealed["tracklet_source_sha256"]}.items():
        residual.checked(residual.RELEASE / "src" / name, pin)

    import held_cfo_features as feature
    import signed_cfo_time_readout as signed
    from leo.analysis.localization_v3 import tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    if (Path(tracks.__file__).resolve() != residual.RELEASE / "src/leo/analysis/localization_v3/tracks.py"
            or Path(feature.__file__).resolve() != here / "held_cfo_features.py"
            or held.odd.WINDOWS != ((250, 2), (2250, 6)) or held.odd.PERIOD != 40_000/3):
        raise ValueError("Require the same released CFO and Graph numerical functions")
    config = TrackConfig(**residual.read(residual.RELEASE / "assets/tracks.json", residual.CONFIG)["config"])
    total = residual.clock()
    plan = residual.read(CAMPAIGN / "plan.json", PLAN)
    order = [*plan["smoke"], *(row["case"] for row in plan["cases"] if row["case"] not in plan["smoke"])]
    if order[RANK - 1] != CASE:
        raise ValueError("The original rank-68 assignment changed")
    entry, = [row for row in plan["cases"] if row["case"] == CASE]
    pair = residual.read(ROOT / "pair.json", pair_pin)
    with (CAMPAIGN / "rows.jsonl").open("rb") as stream:
        rows = [json.loads(line) for line in stream if CASE.encode() in line]
    attempts = closed_roles(entry, pair, rows)
    source = residual.read(ROOT / "authority.json", pair["authority_sha256"])
    candidate_root = ROOT / "successor" / f"attempt-{pair['generation']:06d}"
    run = residual.read(candidate_root / "result.json", attempts["successor"])
    if (run["outcome"] != "complete" or run["process"]["exit_code"] or run["algorithm"] != "successor"
            or run["generation"] != pair["generation"] or run["raw_identity"] != source
            or run["authority_sha256"] != pair["authority_sha256"]):
        raise ValueError("The sealed successor attempt does not bind the original acquisition")
    pub = candidate_root / "publication"
    raw = signed.document(pub / "unified-short-bootstrap.json")
    mixed, witness, _ = signed.qualified_candidate(pub, raw, run["native_sha256"], source["region_sha256"])
    recipe = raw["held_anchor_route"]["receiver_recipe"]
    detail = witness["evidence"]["detail"]
    if (recipe["rule"] != ["full", *(["short_primary"]*7)]
            or recipe["streams"] != ["edge", "channel", "actual_rf_hz"]
            or raw["receiver_audit"]["recording_authority"] != source["raw_authority_sha256"]
            or mixed["source"]["raw_recording_authority_digest"] != source["raw_authority_sha256"]
            or detail["terminal_sha256"] != run["evidence"]["receipt"]["terminal_sha256"]):
        raise ValueError("Require the original one-in-eight receiver and ordinary publication")

    started = residual.clock()
    prior = feature.derive(mixed, config)
    masked_time = residual.elapsed(started)
    started = residual.clock()
    ordinary = tracks.prepare_tracks(mixed, config)
    graph_time = residual.elapsed(started)
    archived = witness["ports"]["graph"]["graph"]
    if len(ordinary["tracks"]) != archived["tracks"] or ordinary["graph_points"] != archived["assigned"]:
        raise ValueError("Reconstructed ordinary Graph differs from the archived membership totals")
    edits = prior.edits
    observed = signed.opportunities(mixed)
    if any(oid not in observed or not observed[oid]["short"] for oid in edits):
        raise ValueError("Only original short winners may enter the projection")
    started = residual.clock()
    revised, proof = development.project_tracks(ordinary, edits)
    projection_time = residual.elapsed(started)
    candidate = dict(case=CASE, rank=RANK, pair_sha256=pair_pin, rule_sha256=RULE, enrollment_sha256=PLAN,
                     mixed_native_sha256=run["native_sha256"], prior_edits_sha256=residual.digest(edits),
                     masked_graph=prior.masked_graph, projected=proof,
                     graph=dict(tracks=archived["tracks"], assigned=archived["assigned"]))
    candidate_json = json.dumps(candidate, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    with candidate_seal.open("xb") as target:
        target.write(candidate_json)
        target.flush()
        os.fsync(target.fileno())
    candidate_seal.chmod(0o444)

    started = residual.clock()
    legacy = development.legacy
    with patch.object(legacy, "CASES", {CASE: (pair_pin, len(edits))}):
        installed, field = legacy.installed(CASE, mixed, signed)
    full = signed.opportunities(installed)
    signed.bind_pair(installed, mixed, full, observed)
    previous = development.metric.matched_rows(edits, observed, full, held.aligned_errors)
    after = [None if row is None else (
        row[0], revised[oid] - full[oid]["factor"][residual.HERTZ], row[2]) for oid, row in previous.items()]
    args = (held.evaluate, held.odd.WINDOWS, signed.ALIAS)
    previous_score = development.metric.summarize(list(previous.values()), *args)
    projected_score = development.metric.summarize(after, *args)
    if any(previous_score[key] != projected_score[key] for key in ("eligible", "scored", "installed_empty", "original")):
        raise ValueError("Both carrier comparisons require all original proposed opportunities")
    return dict(case=CASE, execution_rank=RANK, actual_field_order=pair["actual_order"], field=field,
                development_sha256=DEVELOPMENT, candidate=candidate,
                candidate_seal_sha256=sha256(candidate_json).hexdigest(),
                matched_rows_sha256=residual.digest(previous), projected_rows_sha256=residual.digest(after),
                previous_half_blend=previous_score, moment_preserving=projected_score,
                clocks=dict(masked_graph=masked_time, ordinary_graph=graph_time, projection=projection_time,
                            installed_comparison=residual.elapsed(started), total=residual.elapsed(total)),
                waveform_reads=0, archive_reads=0, survey_reads=0, receiver_runs=0, solver_runs=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-pin", required=True)
    parser.add_argument("--candidate-seal", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.pair_pin, args.candidate_seal), sort_keys=True, indent=2, allow_nan=False))
