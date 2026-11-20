"""Release the second waveform site's scores only after all three solvers seal predictions."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants.compact_tile_interior import margin
from . import screening_figures
from . import waveform_holdout_trial as trial
from . import waveform_site_interior as interior
from . import waveform_site_results as site

CONDITIONS = {
    "containing": "25 km containing",
    "omitted": "25 km near omitted",
    "far-omitted": "25 km far omitted",
}
MATCH = ("input_sha256", "native_sha256", "catalogue_sha256")
LIMIT = [[str(trial.stock.MEMORY), "0"]]
ORIGINAL = "waveform_v5_original"
read, digest = trial.stock.read, trial.stock.digest


def bind_predictions(rows, requests, methods):
    actual = {(r["id"], r["method"]): r for r in rows}
    expected = {(r["id"], method): r for r in requests for method in methods}
    if actual.keys() != expected.keys() or len(actual) != len(rows):
        raise ValueError("sealed receiver outputs changed the planned offer/method roster")
    for key, row in actual.items():
        req = expected[key]
        hashes = (trial.stock.raw_digest(encoded(req)), req["native_sha256"], req["catalog_sha256"])
        if tuple(row[k] for k in MATCH) != hashes:
            raise ValueError("position receipt is not bound to the same scientific request")
        result = row["result"]
        validate_result(result)
        if (
            row["method"] in trial.METHODS
            and result["status"] in ("ok", "withheld")
            and row.get("verified_limits") != LIMIT
        ):
            raise ValueError("numerical solve lacks effective memory and swap proof")
    return actual


def classified_detector(ledger, visits):
    score, details = site.detection_score(ledger, visits)
    stress = {
        name: Counter()
        for name in ("without_ofdm", "with_ofdm", "activity_gap", "faded", "unfaded")
    }
    for r in details:
        v = visits[r["visit"]]
        plant = v["planted"][r["lane"]]
        r.update(
            ofdm=v["burst"] is not None,
            activity_gap=v["activity_gap"],
            fade_amplitude=v["fade_amplitude"],
        )
        summary = Counter(probes=1, probes_with_gate_winner=int(r["gate_positives"] > 0))
        if plant is not None:
            summary.update(
                planted_probes=1,
                winner_hits=int(r["winner_hit"]),
                any_candidate_hits=int(r["any_candidate_hit"]),
            )
        else:
            summary.update(
                no_emission_probes=1, no_emission_gate_positives=int(r["gate_positives"] > 0)
            )
        stress["with_ofdm" if r["ofdm"] else "without_ofdm"].update(summary)
        if r["activity_gap"]:
            stress["activity_gap"].update(summary)
        elif plant is not None:
            stress["faded" if r["fade_amplitude"] < 1 else "unfaded"].update(summary)
    return dict(score, stress=stress), details


def region_scores(positions, requests, scene):
    out, queries = [], []
    conditions = scene["conditions"]
    if len(conditions) != 3 or set(conditions.values()) != CONDITIONS.keys():
        raise ValueError("custodian labels changed the three predeclared regional conditions")
    truth = scene["coordinate"]
    for req in requests:
        ident = req["id"]
        name = conditions[ident]
        center = req["tile"]
        if center != scene["offers"][name] or center != req["screen_center"]:
            raise ValueError("sealed numerical offer differs from the blind regional menu")
        term = dict(center=center, width_km=25.0)
        offset = margin(truth, term)
        if (offset > 0) != (name == "containing"):
            raise ValueError("offer label differs from exact compact region geometry")
        rows = [r for (i, _), r in positions.items() if i == ident]
        first = rows[0]
        bindings = {k: first[k] for k in MATCH if first[k] is not None}
        queries.append(
            dict(
                id=ident,
                recording="Second simulated waveform site",
                condition=name,
                truth=truth,
                bindings=bindings,
            )
        )
        for row in rows:
            result = row["result"]
            for arm in ARMS:
                fit = result["arms"][arm]
                point, forced = fit["latlon"], fit.get("forced_latlon")
                err = distance_km(point, truth)
                out.append(
                    dict(
                        id=ident,
                        method=row["method"],
                        condition=name,
                        arm=arm,
                        status=result["status"],
                        reason=result.get("reason"),
                        published=point is not None,
                        false_publication=point is not None and offset <= 0,
                        legitimate_within_5km=offset > 0 and err is not None and err <= 5.0,
                        position_error_km=err,
                        forced_error_km=distance_km(forced, truth),
                        rf_rms_hz=fit.get("rf_rms_hz"),
                        true_face_margin_km=offset,
                        terminal_face_margin_km=margin(point if point is not None else forced, term)
                        if point is not None or forced is not None
                        else None,
                        offer_center_error_km=distance_km(truth, center),
                        worker_wall_s=row.get("worker_wall_s"),
                        worker_cpu_s=row.get("worker_cpu_s"),
                        peak_rss_kib=row.get("peak_rss_kib"),
                        cgroup_peak_bytes=row.get("worker_cgroup_peak_bytes"),
                    )
                )
    return out, queries


def earlier_site():
    root = trial.REPORT.parents[1]
    original = trial.stock.REPORT
    trial.stock.sealed(original, "score-lock.json")
    score = read(original / "scores.json")
    earlier = [
        (original / "figure-queries.json", read(original / "figure-queries.json")[0]["truth"])
    ]
    for name, key in (("compact-blind", "targets"), ("boundary-policy", "labels")):
        path = root / "receiver-core" / name / "truth-after-lock.json"
        earlier.extend((path, r["site"]) for r in read(path)[key].values())
    path = root / "site-transfer/labels.json"
    earlier.extend((path, r["latlon"]) for r in read(path).values() if r.get("latlon") is not None)
    return score, earlier


def cross_site(position, detector, truth):
    prior, earlier = earlier_site()
    root = trial.REPORT.parents[1]
    nearest, path = min((distance_km(pt, truth), p) for p, pt in earlier)
    return dict(
        descriptive_only=True,
        previous_waveform_score_lock_sha256=digest(trial.stock.REPORT / "score-lock.json"),
        checked_prior_panels=sorted({str(p.relative_to(root)) for p, _ in earlier}),
        checked_unique_prior_locations=len({tuple(point) for _, point in earlier}),
        nearest_earlier_simulated_site_km=nearest,
        nearest_earlier_panel=str(path.relative_to(root)),
        pilot_only_site_distance_km=distance_km(earlier[0][1], truth),
        previous_detector_counts=prior["detector"]["counts"],
        held_detector_counts=detector["counts"],
        previous_position=prior["position"],
        held_position=[r for r in position if r["method"] == trial.METHODS[0]],
    )


def score(work, out, reference_lock, reference_filename):
    if (out / "score-lock.json").exists():
        raise FileExistsError("holdout score already sealed")
    prediction = trial.stock.sealed(out, "prediction-lock.json")
    detector = trial.stock.sealed(out, "detector-lock.json")
    authority = trial.stock.sealed(out, "input-lock.json")
    ref = trial.stock.sealed(reference_lock.parent, reference_lock.name)
    if set(ref["cases"]) != set(prediction["cases"]) or reference_filename not in ref["files"]:
        raise ValueError("independent original reference has not sealed the same complete roster")
    reference_rows = site.read_rows(reference_lock.parent / reference_filename)
    if {r["method"] for r in reference_rows} != {ORIGINAL}:
        raise ValueError("expected the prespecified independent original numerical reference")
    requests = read(out / "requests.json")
    base_rows = site.read_rows(out / "positions.jsonl.gz")
    positions = bind_predictions(base_rows + reference_rows, requests, (*trial.METHODS, ORIGINAL))
    private_path = work / "custodian.json"
    if digest(private_path) != authority["private_sha256"]:
        raise ValueError("custodian labels differ from their prospective commitment")
    private = read(private_path)
    if trial.stock.raw_digest(bytes.fromhex(private["seed"])) != authority["seed_sha256"]:
        raise ValueError("unblinded seed differs from the committed seed")
    ledger = site.read_rows(out / "visit-ledger.jsonl.gz")
    if len(ledger) != detector["completed_visits"]:
        raise ValueError("detector completion ledger changed")
    scores, details = classified_detector(ledger, private["visits"])
    scores.update(wall_s=detector["worker_wall_s"])
    geographic, queries = region_scores(positions, requests, private["scene"])
    parity = []
    for req in requests:
        first, second = [positions[req["id"], method]["result"] for method in trial.METHODS]
        parity.append(
            dict(id=req["id"], exact_guard_and_fit_parity=interior.exact_parity(second, first, req))
        )
    save_json(out / "scores.json", dict(detector=scores, position=geographic, guard_parity=parity))
    save_json(
        out / "cross-site.json", cross_site(geographic, scores, private["scene"]["coordinate"])
    )
    save_json(out / "figure-queries.json", dict(queries=queries))
    trial.stock.pack(out, "planted-hit-ledger.jsonl.gz", details)
    write(out / "truth-after-lock.json.gz", gzip.compress(private_path.read_bytes(), mtime=0))
    write(
        out / "reference-positions.jsonl.gz",
        (reference_lock.parent / reference_filename).read_bytes(),
    )
    write(out / "reference-prediction-lock.json", reference_lock.read_bytes())
    names = (
        "prediction-lock.json",
        "positions.jsonl.gz",
        "reference-positions.jsonl.gz",
        "reference-prediction-lock.json",
        "figure-queries.json",
        "scores.json",
        "cross-site.json",
        "detector-lock.json",
        "planted-hit-ledger.jsonl.gz",
        "truth-after-lock.json.gz",
    )
    save_json(
        out / "score-lock.json",
        dict(cases=prediction["cases"], files={n: digest(out / n) for n in names}),
    )
    figures(out, ORIGINAL)


def figures(out, original):
    labels = {
        trial.METHODS[0]: "Phase release",
        trial.METHODS[1]: "20 m interior",
        original: "Original v5 reference",
    }
    original_series = dict(
        key="stock",
        label=labels[original],
        file="reference-positions.jsonl.gz",
        value=original,
        match=list(MATCH),
    )
    specs = []
    for i, method in enumerate(trial.METHODS):
        control = trial.METHODS[0]
        candidate = dict(
            key="candidate", label=labels[method], file="positions.jsonl.gz", value=method
        )
        if i == 0:
            comparison = original_series
        else:
            candidate["forced_label"] = "Interior forced fit"
            comparison = dict(
                key="stock",
                label=labels[control],
                file="positions.jsonl.gz",
                value=control,
                match=list(MATCH),
            )
        specs.append(
            dict(
                id=f"waveform-holdout-{('phase-release', 'interior')[i]}",
                method=method,
                scope="transfer",
                title=f"{labels[method]} on a blind stressed Qin waveform site",
                caption=(
                    "One simulated site with twelve revised emitter orbits and dual 10 MS/s CI16. "
                    "Visits include fades, gaps and OFDM. All offers share stock GLRT factors. "
                    "Publishing in either omitted region counts as a false fix."
                ),
                cases="sealed",
                seal="score-lock.json",
                queries="figure-queries.json",
                provenance=[
                    "prediction-lock.json",
                    "scores.json",
                    "reference-prediction-lock.json",
                ],
                condition_labels=CONDITIONS,
                series=[candidate, comparison],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=specs))
    screening_figures.generate(out / "charts", methods=list(trial.METHODS), evidence=out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    p.add_argument("--reference-lock", required=True, type=Path)
    p.add_argument("--reference-filename", default="positions.jsonl.gz")
    args = p.parse_args()
    score(args.work, args.out, args.reference_lock, args.reference_filename)


if __name__ == "__main__":
    main()
