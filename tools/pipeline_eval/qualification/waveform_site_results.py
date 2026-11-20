"""Score blinded waveform-site outputs after both installed receiver offers are terminal."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants.compact_tile_interior import margin
from . import screening_figures
from . import waveform_site_model as model
from . import waveform_site_trial as trial

ALIAS_HZ = 1 / 4.4e-6
MAX_EPOCH_SAMPLES = 2
MAX_CFO_HZ = 1000


def read_rows(path):
    with gzip.open(path, "rt") as f:
        return list(map(json.loads, f))


def circular(value, period):
    return (value + period / 2) % period - period / 2


def residual(candidate, planted):
    phase = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
    return (
        circular(phase - planted["epoch"], planted["period"]),
        circular(candidate["fractional_tracking_cfo_hz"] - planted["cfo_model_hz"], ALIAS_HZ),
    )


def hit(pair):
    return abs(pair[0]) <= MAX_EPOCH_SAMPLES and abs(pair[1]) <= MAX_CFO_HZ


def detection_score(ledger, visits):
    observed, emitters = Counter(), defaultdict(Counter)
    lanes = {str(i): Counter() for i in range(2)}
    channel_counts = defaultdict(Counter)
    planted_count = sum(p is not None for v in visits for p in v["planted"])
    matches, epochs, mismatches, details = [], [], [], []
    used = set()
    for measured in ledger:
        j = measured["visit"]
        if j in used or measured["nbytes"] != model.SAMPLES * 2 * 2 * 2:
            raise ValueError("duplicate visit or different dual-CI16 native probe width")
        used.add(j)
        private = visits[j]
        if private["visit"] != j or [p["receiver_id"] for p in measured["probes"]] != [0, 1]:
            raise ValueError("waveform ledger and scheduled paired probe disagree")
        for lane, (p, plant) in enumerate(zip(measured["probes"], private["planted"], strict=True)):
            if (p["visit_index"], p["channel"], p["actual_rf_hz"]) != (
                j,
                private["channel"],
                private["rf_hz"],
            ):
                raise ValueError("projection changed the detector visit/RF binding")
            passing = [c for c in p["candidates"] if c["passed_fractional_margin_gate"] is True]
            winner = max(
                passing, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None
            )
            counts = Counter(complete_probes=1, gate_positives=int(winner is not None))
            row = dict(visit=j, lane=lane, channel=p["channel"], gate_positives=len(passing))
            if plant is None:
                counts.update(
                    no_emission_probes=1, no_emission_gate_positives=int(winner is not None)
                )
            else:
                errors = [residual(c, plant) for c in passing]
                win_error = residual(winner, plant) if winner is not None else None
                won = win_error is not None and hit(win_error)
                any_hit = any(map(hit, errors))
                counts.update(
                    planted_probes=1,
                    any_candidate_hits=int(any_hit),
                    winner_hits=int(won),
                    wrong_winners=int(winner is not None and not won),
                    no_gate_winner=int(winner is None),
                )
                emitters[str(plant["norad"])].update(counts)
                mismatches.append(abs(plant["catalogue_mismatch_hz"]))
                if won:
                    epochs.append(abs(win_error[0]))
                    matches.append(abs(win_error[1]))
                row.update(
                    planted_norad=plant["norad"],
                    any_candidate_hit=any_hit,
                    winner_hit=won,
                    winner_residual=win_error,
                    catalogue_mismatch_hz=plant["catalogue_mismatch_hz"],
                )
            observed.update(counts)
            lanes[str(lane)].update(counts)
            channel_counts[str(p["channel"])].update(counts)
            details.append(row)
    return dict(
        scheduled_dual_rx_probes=2 * len(visits),
        scheduled_planted_probes=planted_count,
        scheduled_no_emission_probes=2 * len(visits) - planted_count,
        counts=dict(observed),
        by_receiver=lanes,
        by_channel=channel_counts,
        by_planted_norad=emitters,
        winner_abs_phase_error_samples=distribution(epochs),
        winner_abs_cfo_error_hz=distribution(matches),
        projected_abs_causal_vs_truth_hz_all_plantings=distribution(mismatches),
        emitted_ci16_bytes=sum(r["nbytes"] for r in ledger),
        generation_cpu_s_total=sum(r["generation_cpu_s"] for r in ledger),
        detector_cpu_s_total=sum(r["detector_cpu_s"] for r in ledger),
        detector_cpu_s_per_visit=distribution(r["detector_cpu_s"] for r in ledger),
    ), details


def position_rows(rows, requests, private):
    scene = private["scene"]
    cases = {r["id"]: r for r in requests}
    conditions = scene["conditions"]
    ids = [r["id"] for r in rows]
    if (
        len(ids) != 2
        or set(ids) != set(cases)
        or set(conditions.values()) != {"containing", "omitted"}
    ):
        raise ValueError("both blinded offers must finish and bind to the two real conditions")
    scored, queries = [], []
    for row in rows:
        ident = row["id"]
        condition, case = conditions[ident], cases[ident]
        request_sha = trial.raw_digest(encoded(case))
        if (
            row["method"] != trial.METHOD
            or row["input_sha256"] != request_sha
            or row["native_sha256"] != case["native_sha256"]
            or row["catalogue_sha256"] != case["catalog_sha256"]
            or case["tile"] != scene["offers"][condition]
        ):
            raise ValueError("installed position prediction has a mismatched scientific request")
        validate_result(row["result"])
        site = scene["coordinate"]
        tile = dict(center=case["tile"], width_km=25.0)
        face = margin(site, tile)
        if (face > 0) != (condition == "containing"):
            raise ValueError("sealed offer and exact fitted-region basis disagree")
        for arm in ARMS:
            result = row["result"]
            arm_result = result["arms"][arm]
            position = arm_result["latlon"]
            forced = arm_result.get("forced_latlon")
            error = distance_km(site, position)
            scored.append(
                dict(
                    id=ident,
                    condition=condition,
                    arm=arm,
                    status=result["status"],
                    reason=result.get("reason"),
                    published=position is not None,
                    false_publication=position is not None and condition == "omitted",
                    within_5km=error is not None and error <= 5,
                    position_error_km=error,
                    forced_error_km=distance_km(site, forced),
                    rf_rms_hz=arm_result.get("rf_rms_hz"),
                    truth_face_margin_km=face,
                    position_face_margin_km=margin(position, tile)
                    if position is not None
                    else None,
                    offer_center_error_km=distance_km(site, tile["center"]),
                    wall_s=row["worker_wall_s"],
                    cpu_s=row["worker_cpu_s"],
                    peak_rss_kib=row["peak_rss_kib"],
                )
            )
        bindings = dict(input_sha256=request_sha, catalogue_sha256=row["catalogue_sha256"])
        if row["native_sha256"] is not None:
            bindings["native_sha256"] = row["native_sha256"]
        queries.append(
            dict(
                id=ident,
                recording="Simulated waveform site",
                condition=condition,
                truth=site,
                bindings=bindings,
            )
        )
    return scored, queries


def score(work, out):
    if (out / "score-lock.json").exists():
        raise FileExistsError("unblinded waveform qualification already sealed")
    prediction = trial.sealed(out, "prediction-lock.json")
    detector = trial.sealed(out, "detector-lock.json")
    input_lock = trial.sealed(out, "input-lock.json")
    private_path = work / "custodian.json"
    if trial.digest(private_path) != input_lock["private_sha256"]:
        raise ValueError("the scorer cannot open labels differing from the prospective commitment")
    rows = read_rows(out / "positions.jsonl.gz")
    if [r["id"] for r in rows] != prediction["cases"]:
        raise ValueError("position receipt differs from the sealed planned offers")
    requests = trial.read(out / "requests.json")
    if detector["ready"] and {r["native_sha256"] for r in requests} != {
        trial.raw_digest(gzip.decompress((out / "native.json.gz").read_bytes()))
    }:
        raise ValueError(
            "the position inputs are not the complete emitted-waveform detector document"
        )
    private = trial.read(private_path)
    if trial.raw_digest(bytes.fromhex(private["seed"])) != input_lock["seed_sha256"]:
        raise ValueError("unblinded seed differs from the seed commitment")
    ledger = read_rows(out / "visit-ledger.jsonl.gz")
    if len(ledger) != detector["completed_visits"]:
        raise ValueError("waveform detector coverage differs from its sealed accounting")
    detector_scores, details = detection_score(ledger, private["visits"])
    position_scores, queries = position_rows(rows, requests, private)
    paired = {}
    for condition in ("containing", "omitted"):
        a, b = [r for r in position_scores if r["condition"] == condition]
        paired[condition] = {
            k: None if a[k] is None or b[k] is None else b[k] - a[k]
            for k in ("position_error_km", "forced_error_km", "rf_rms_hz")
        }
    scores = dict(
        position=position_scores,
        fitted_minus_c0=paired,
        detector=dict(detector_scores, wall_s=detector["worker_wall_s"]),
    )
    save_json(out / "scores.json", scores)
    save_json(out / "figure-queries.json", queries)
    trial.pack(out, "planted-hit-ledger.jsonl.gz", details)
    write(out / "truth-after-lock.json.gz", gzip.compress(private_path.read_bytes(), mtime=0))
    names = (
        "prediction-lock.json",
        "detector-lock.json",
        "scores.json",
        "planted-hit-ledger.jsonl.gz",
        "truth-after-lock.json.gz",
        "figure-queries.json",
        "positions.jsonl.gz",
    )
    save_json(
        out / "score-lock.json",
        dict(cases=prediction["cases"], files={n: trial.digest(out / n) for n in names}),
    )
    chart(out, scores)
    return scores


def chart(out, scores):
    scored = trial.sealed(out, "score-lock.json")
    queries = trial.read(out / "figure-queries.json")
    save_json(out / "chart-queries.json", dict(queries=queries))
    names = ("chart-queries.json", "score-lock.json", *scored["files"])
    save_json(
        out / "figure-lock.json",
        dict(cases=scored["cases"], files={n: trial.digest(out / n) for n in names}),
    )
    captions = []
    for condition, label in (("containing", "Containing offer"), ("omitted", "Omitted offer")):
        selected = [r for r in scores["position"] if r["condition"] == condition]
        status = selected[0]["status"].replace("_", " ")
        count = sum(r["published"] for r in selected)
        captions.append(f"{label} published {count}/2 calibration arms ({status}).")
    caption = (
        "One simulated site. Qin dual-CI16 samples at 10 MS/s went through the stock wide GLRT and "
        "the installed phase release. Each 25 km region used the same causal TLE. "
        + " ".join(captions)
    )
    spec = dict(
        id="waveform-site-phase-release",
        method=trial.METHOD,
        scope="transfer",
        cases="sealed",
        title="Stock wide GLRT to installed phase release on new-location waveform",
        caption=caption,
        seal="figure-lock.json",
        queries="chart-queries.json",
        provenance=["prediction-lock.json", "detector-lock.json", "scores.json"],
        condition_labels={
            "containing": "25 km containing offer",
            "omitted": "25 km near-omitted offer",
        },
        series=[
            dict(
                key="candidate",
                label="Installed phase release",
                file="positions.jsonl.gz",
                value=trial.METHOD,
            )
        ],
    )
    save_json(out / "figures.json", dict(version=1, charts=[spec]))
    screening_figures.generate(out / "charts", methods=[trial.METHOD], evidence=out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    args = p.parse_args()
    score(args.work, args.out)


if __name__ == "__main__":
    main()
