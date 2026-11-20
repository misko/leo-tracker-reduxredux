"""Score the blinded hybrid background, negative control and region decisions."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants.compact_tile_interior import margin
from . import hybrid_site_trial as trial
from . import screening_figures
from . import waveform_site_interior as interior
from . import waveform_site_results as pilot

REFERENCE_METHOD = "hybrid_original_v5"
REF_ROSTER = ("hybrid", "donor-only")
CONTROL = "donor-only"
CONDITIONS = {"containing": "25 km containing", "omitted": "25 km near omitted"}
MATCH = ("input_sha256", "native_sha256", "catalogue_sha256")
read, digest = trial.stock.read, trial.stock.digest


def eligible(probe):
    return [c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True]


def winner(candidates):
    return max(
        candidates, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None
    )


def matches(candidate, known):
    if candidate is None:
        return False
    for c in known:
        expected = dict(
            epoch=c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"],
            period=trial.model.RATE / 750,
            cfo_model_hz=c["fractional_tracking_cfo_hz"],
        )
        if pilot.hit(pilot.residual(candidate, expected)):
            return True
    return False


def known_donors(out, ledger):
    known = {}
    for case, source in read(out / "donor-plan.json")["donors"].items():
        locator = Path(source["source_authority_native_path"])
        payload = locator.read_bytes()
        if trial.stock.raw_digest(payload) != source["source_authority_native_sha256"]:
            raise ValueError("original archived positive-control factor authority changed")
        native = json.loads(payload)["source"]
        by_counter = {
            (
                r["visit_index"],
                r["receiver_id"],
                r["valid_start_counter"],
                r["edge"],
                r["actual_rf_hz"],
            ): r
            for r in native["probes"]
            if r["probe_start_ms"] == 0
        }
        for visit in ledger:
            meta = visit["donor"]
            if meta["donor"] != case:
                continue
            for lane in range(2):
                key = (
                    meta["donor_global_visit"],
                    lane,
                    meta["donor_sample_start"],
                    meta["edge"],
                    meta["donor_rf_hz"],
                )
                captured = by_counter.get(key)
                if captured is not None:
                    known[visit["visit"], lane] = eligible(captured)
    return known


def detector_scores(ledger, visits, archived):
    summary, per_probe = {}, []
    reference = Counter()
    for visit in ledger:
        j = visit["visit"]
        for lane in range(2):
            old = archived.get((j, lane))
            real = eligible(visit["arms"][CONTROL]["probes"][lane])
            hybrid = winner(eligible(visit["arms"]["hybrid"]["probes"][lane]))
            pulse = visits[j]["planted"][lane]
            hybrid_hit = (
                pulse is not None
                and hybrid is not None
                and pilot.hit(pilot.residual(hybrid, pulse))
            )
            old_hit = old is not None and matches(winner(real), old)
            hybrid_matches_real = matches(hybrid, real)
            reference.update(
                complete_probe_rows=1,
                exact_original_probe_joins=int(old is not None),
                original_probe_joins_with_gate=int(bool(old)),
                donor_only_winner_matches_original=int(old_hit),
                hybrid_winner_matches_donor_only=int(hybrid_matches_real),
                hybrid_false_winner_matches_donor_only=int(hybrid_matches_real and not hybrid_hit),
                hybrid_false_winner_matches_original=int(
                    old is not None and matches(hybrid, old) and not hybrid_hit
                ),
            )
            per_probe.append(
                dict(
                    visit=j,
                    lane=lane,
                    historical_source_probe_join=old is not None,
                    historical_source_gate_candidates=len(old) if old is not None else None,
                    normalized_donor_gate_candidates=len(real),
                    normalized_donor_match_old=old_hit,
                    hybrid_planted_hit=hybrid_hit,
                    hybrid_matches_donor_only=hybrid_matches_real,
                )
            )
    for arm in trial.model.ARMS:
        normalized = [
            dict(
                visit=r["visit"],
                nbytes=r["donor"]["nbytes"],
                generation_cpu_s=r["mix_cpu_s"],
                **r["arms"][arm],
            )
            for r in ledger
        ]
        truth = visits if arm != CONTROL else [dict(v, planted=[None, None]) for v in visits]
        score, _ = pilot.detection_score(normalized, truth)
        summary[arm] = score
    return dict(
        backgrounds=summary,
        archived_source_overlap=reference,
        actual_mix_cpu_s_total=sum(v["mix_cpu_s"] for v in ledger),
    ), per_probe


def bind(rows, independent, requests, schedule_sha):
    combined = list(rows)
    for r in independent:
        if r["method"] != REFERENCE_METHOD or r["cohort"] not in REF_ROSTER:
            raise ValueError("unexpected original numerical reference")
        combined.append(
            dict(r, id=r["offer_id"], variant=r["cohort"], document_sha256=schedule_sha)
        )
    known = {(a, r["id"]): r for a, rs in requests.items() for r in rs}
    expected = {
        (a, i, m)
        for a, i in known
        for m in (*trial.METHODS, *((REFERENCE_METHOD,) if a in REF_ROSTER else ()))
    }
    actual = {(r["variant"], r["id"], r["method"]): r for r in combined}
    if set(actual) != expected or len(combined) != len(actual):
        raise ValueError(
            "terminal predictions differ from the frozen background/offer/method roster"
        )
    proof = [[str(trial.stock.MEMORY), "0"]]
    for (a, ident, method), r in actual.items():
        q = known[a, ident]
        expected_input = (
            trial.stock.raw_digest(encoded(q)),
            q["native_sha256"],
            q["catalog_sha256"],
        )
        if tuple(r[k] for k in MATCH) != expected_input or r["document_sha256"] != schedule_sha:
            raise ValueError("selected position differs from the exact public experimental input")
        validate_result(r["result"])
        if (
            method in trial.METHODS
            and r["result"]["status"] in ("ok", "withheld")
            and r.get("verified_limits") != proof
        ):
            raise ValueError("installed solve lacks effective cgroup proof")
    return actual


def positions(actual, requests, scene, schedule_sha):
    results, labels, compact_parity = [], {}, []
    for variant, rs in requests.items():
        labels[variant] = {}
        for req in rs:
            ident = req["id"]
            condition = scene["conditions"][ident]
            tile = dict(center=req["tile"], width_km=25.0)
            if req["tile"] != scene["offers"][condition] or req["screen_center"] != tile["center"]:
                raise ValueError("offer geometry changed after blinding")
            truth = scene["coordinate"] if variant != CONTROL else None
            labels[variant][ident] = dict(
                truth=truth,
                condition=condition if truth is not None else "donor-only",
                source_offer_condition=condition,
            )
            conditional_face = margin(truth, tile) if truth is not None else None
            if truth is not None and (conditional_face > 0) != (condition == "containing"):
                raise ValueError("truth was scored against the wrong region")
            base, guarded = [actual[variant, ident, m]["result"] for m in trial.METHODS]
            compact_parity.append(
                dict(
                    variant=variant,
                    id=ident,
                    exact_guard_fit=interior.exact_parity(guarded, base, req),
                )
            )
            for (a, i, m), item in actual.items():
                if (a, i) != (variant, ident):
                    continue
                for arm in ARMS:
                    result = item["result"]
                    point = result["arms"][arm]["latlon"]
                    forced = result["arms"][arm].get("forced_latlon")
                    results.append(
                        dict(
                            method=m,
                            id=ident,
                            variant=variant,
                            offer=condition,
                            arm=arm,
                            status=result["status"],
                            reason=result.get("reason"),
                            published=point is not None,
                            false_publication=point is not None
                            and (variant == CONTROL or condition == "omitted"),
                            geography_error_km=distance_km(point, truth),
                            forced_error_km=distance_km(forced, truth),
                            geography_center_prior_error_km=distance_km(req["tile"], truth),
                            true_face_margin_km=conditional_face,
                            terminal_face_margin_km=margin(
                                point if point is not None else forced, tile
                            )
                            if point is not None or forced is not None
                            else None,
                            conditional_rf_rms_hz=result["arms"][arm].get("rf_rms_hz"),
                            worker_wall_s=item.get("worker_wall_s"),
                            worker_cpu_s=item.get("worker_cpu_s"),
                            peak_rss_kib=item.get("peak_rss_kib"),
                            cgroup_peak_bytes=item.get("worker_cgroup_peak_bytes"),
                        )
                    )
    queries = [
        dict(
            id=i,
            recording="Hybrid simulation site",
            condition=v["condition"],
            truth=v["truth"],
            bindings=dict(document_sha256=schedule_sha),
        )
        for i, v in labels["hybrid"].items()
    ]
    return results, labels, compact_parity, queries


def chart_specs(out, counts):
    names = dict(gaussian="Matched Gaussian", hybrid="Recorded background")
    base, interior_method = trial.METHODS
    specs = []

    def series(key, label, method, a, peers):
        return dict(
            key=key,
            label=label,
            file="positions.jsonl.gz",
            value=method,
            where=dict(variant=a),
            match=peers,
        )

    def spec(ident, method, title, caption, pair):
        return dict(
            id=ident,
            method=method,
            title=title,
            caption=caption,
            scope="transfer",
            cases="sealed",
            seal="score-lock.json",
            queries="figure-queries.json",
            provenance=["prediction-lock.json", "scores.json"],
            condition_labels=CONDITIONS,
            series=pair,
        )

    specs.append(
        spec(
            "hybrid-site-recorded-background",
            base,
            "Same Qin emission over recorded or Gaussian backgrounds",
            "One blinded simulated location. Every dual visit receives the same planted emission. "
            "Both backgrounds share RMS and region offers. "
            "Publishing in the omitted region is a false fix.",
            [
                series("candidate", names["hybrid"], base, "hybrid", []),
                series("stock", names["gaussian"], base, "gaussian", ["document_sha256"]),
            ],
        )
    )
    for a in ("hybrid", "gaussian"):
        candidate = series("candidate", "20 m interior", interior_method, a, [])
        candidate["forced_label"] = "Interior forced fit"
        specs.append(
            spec(
                f"hybrid-site-{a}-interior",
                interior_method,
                f"Prospective 20 m policy on {names[a].lower()} IQ",
                "Both installed profiles share the same native detections and 25 km regions. "
                "Forced fits are diagnostic coordinates retained after withdrawal.",
                [candidate, series("stock", "Phase release", base, a, list(MATCH))],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=specs))
    screening_figures.generate(out / "charts", evidence=out)
    stage_chart(out, counts)


def stage_chart(out, summary):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.2), layout="constrained")
    colors = ["#145d53", "#a66230", "#658191"]
    names = ("Recorded + Qin", "Gaussian + Qin", "Donor-only")
    d = [summary["backgrounds"][key]["counts"] for key in trial.model.ARMS]
    for a, head, k, total, idx in (
        (
            ax[0],
            "Planted waveform in observation winner",
            "winner_hits",
            "planted_probes",
            range(2),
        ),
        (
            ax[1],
            "Gate winners in probes without a plant",
            "no_emission_gate_positives",
            "no_emission_probes",
            range(3),
        ),
    ):
        a.barh(
            [names[i] for i in idx],
            [100 * d[i].get(k, 0) / d[i][total] for i in idx],
            color=[colors[i] for i in idx],
        )
        for j in idx:
            value = 100 * d[j].get(k, 0) / d[j][total]
            a.text(
                2 if value >= 35 else value + 2,
                j,
                f"{d[j].get(k, 0)} / {d[j][total]}",
                va="center",
                color="white" if value >= 35 else "black",
            )
        a.set_xlim(0, 100)
        a.set_title(head, fontsize=11)
        a.set_xlabel("Percent of receiver probes")
        a.invert_yaxis()
        a.grid(axis="x", alpha=0.22)
    fig.suptitle("Stock wide GLRT on matched dual CI16 waveform backgrounds")
    fig.savefig(out / "detector-evidence.png", dpi=180)
    plt.close(fig)


def score(work, out, reference):
    if (out / "score-lock.json").exists():
        raise FileExistsError("hybrid site scored already")
    pred = trial.stock.sealed(out, "prediction-lock.json")
    det = trial.stock.sealed(out, "detector-lock.json")
    locked = trial.stock.sealed(out, "input-lock.json")
    reref = trial.stock.sealed(reference.parent, reference.name)
    if set(reref["cases"]) != {f"{a}-{i}" for a in REF_ROSTER for i in pred["cases"]}:
        raise ValueError("original reference has not finished the frozen hybrid and null offers")
    independent = pilot.read_rows(reference.parent / "positions.jsonl.gz")
    requests = {a: read(out / a / "requests.json") for a in trial.model.ARMS}
    for a in requests:
        trial.stock.sealed(out / a, "detector-lock.json")
    schedule_sha = digest(out / "schedule.json")
    actual = bind(pilot.read_rows(out / "positions.jsonl.gz"), independent, requests, schedule_sha)
    labels = work / "custodian.json"
    if digest(labels) != locked["private_sha256"]:
        raise ValueError("private labels do not match their prospective hash")
    private = read(labels)
    if trial.stock.raw_digest(bytes.fromhex(private["seed"])) != locked["seed_sha256"]:
        raise ValueError("private seed differs from prospective commitment")
    ledger = pilot.read_rows(out / "visit-ledger.jsonl.gz")
    if len(ledger) != det["completed_visits"]:
        raise ValueError("complete measured samples missing from the hybrid ledger")
    counts, attribution = detector_scores(ledger, private["visits"], known_donors(out, ledger))
    counts["stage_wall_s"] = det["worker_wall_s"]
    result, by_arm, parity, queries = positions(actual, requests, private["scene"], schedule_sha)
    save_json(out / "scores.json", dict(positions=result, detector=counts, guard_parity=parity))
    save_json(
        out / "truth-after-lock.json", dict(targets=by_arm["hybrid"], targets_by_background=by_arm)
    )
    write(out / "custodian-after-lock.json.gz", gzip.compress(labels.read_bytes(), mtime=0))
    save_json(out / "figure-queries.json", dict(queries=queries))
    trial.stock.pack(out, "donor-source-audit.jsonl.gz", attribution)
    write(out / "reference-prediction-lock.json", reference.read_bytes())
    files = (
        "prediction-lock.json",
        "detector-lock.json",
        "scores.json",
        "positions.jsonl.gz",
        "truth-after-lock.json",
        "figure-queries.json",
        "donor-source-audit.jsonl.gz",
        "custodian-after-lock.json.gz",
        "reference-prediction-lock.json",
    )
    save_json(
        out / "score-lock.json",
        dict(cases=pred["cases"], files={n: digest(out / n) for n in files}),
    )
    chart_specs(out, counts)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    p.add_argument("--reference", type=Path, required=True)
    args = p.parse_args()
    score(args.work, args.out, args.reference)


if __name__ == "__main__":
    main()
