"""Validate full raw-point accounting, prior causality and residual compatibility."""

import csv
import hashlib
import json

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from run_s01_shared_satellite_prototypes import OUTPUT, RAW, ROOT, Prototype, make_priors


def run():
    priors, tles = make_priors()
    summaries = json.loads((OUTPUT / "summary.json").read_text())
    baseline = {}
    controls = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        experiment = Prototype("family_extension", fc, priors, tles)
        initial = experiment.expectation()
        ids = {
            oid
            for t, r in zip(experiment.tracks, initial["rows"], strict=True)
            if r["compatible"]
            for oid in t["observation_ids"]
        }
        expected = set(experiment.old["associated_observation_ids"])
        assert ids == expected and len(ids) == 2608
        controls[arm] = dict(
            points=len(ids),
            same_original_ids=True,
            same_original_labels=all(
                r["candidate_norad"] == old["candidate_norad"]
                for r, old in zip(initial["rows"], experiment.oldrows, strict=True)
                if r["compatible"] and old["compatible"]
            ),
        )
        baseline[arm] = experiment.old
        if not fc:
            tracks = experiment.tracks
            curved = set(experiment.study.curved_keys)
    raw = {
        r["observation_id"]: r
        for line in RAW.read_text().splitlines()
        if (r := json.loads(line))["source_id"] == "S01"
    }
    mapping = {t["key"]: t for t in tracks}
    graph_ids = {oid for t in tracks for oid in t["observation_ids"]}
    assert len(graph_ids) == 4486 and len(raw) == 4797
    for t in tracks:
        for oid, time, value in zip(t["observation_ids"], t["times"], t["values"], strict=True):
            assert raw[oid]["time_s"] == time
            alias = (value - raw[oid]["measured_cfo_hz"]) / matching.PERIOD
            assert abs(alias - round(alias)) < 1e-8
    families, audit = [], []
    results = {}
    for summary in summaries:
        method, arm = summary["method"], summary["arm"]
        folder = OUTPUT / method / arm
        association = json.loads((folder / "association.json").read_text())
        parameters = json.loads((folder / "parameters.json").read_text())
        rows = association["rows"]
        ids, loose = map(
            set,
            (
                association["associated_observation_ids"],
                association["unassociated_observation_ids"],
            ),
        )
        assert ids | loose == raw.keys() and not ids & loose and ids <= graph_ids
        expected = {
            oid
            for r in rows
            if r["compatible"]
            for oid in mapping[r["component"]]["observation_ids"]
        }
        assert ids == expected and len(ids) == summary["associated"]
        old_ids = set(baseline[arm]["associated_observation_ids"])
        assert len(ids - old_ids) == summary["gained"]
        assert len(old_ids - ids) == summary["lost"]
        old_labels = {r["component"]: r for r in baseline[arm]["association"]["rows"]}
        for r in rows:
            assert r["points"] == len(mapping[r["component"]]["times"])
            noise = matching.noise_screen(r["residual_hz"], r["times_s"])
            if r["compatible"]:
                assert noise["noise_screen_pass"]
                assert r["rms_hz"] <= 450 and abs(r["bias_hz"]) <= 3000
            old = old_labels[r["component"]]
            if method == "family_extension" and old["compatible"] and old["active_curvature"]:
                assert r["compatible"] and r["candidate_norad"] == old["candidate_norad"]
        for parameter in parameters.values():
            members = parameter["calibration_members"]
            assert all(k in curved for k in members)
            if members:
                assert len({mapping[k]["channel"] for k in members}) >= 2
        for n in sorted({r["candidate_norad"] for r in rows if r["compatible"]}):
            own = [r for r in rows if r["compatible"] and r["candidate_norad"] == n]
            active = [r for r in own if r["active_curvature"]]
            pool = None
            if active:
                time = np.concatenate([r["times_s"] for r in active])
                residual = np.concatenate([r["residual_hz"] for r in active])
                order = np.argsort(time, kind="stable")
                pool = matching.noise_screen(residual[order], time[order])
            families.append(
                dict(
                    method=method,
                    arm=arm,
                    norad=n,
                    fragments=len(own),
                    points=sum(r["points"] for r in own),
                    curved_fragments=len(active),
                    curved_points=sum(r["points"] for r in active),
                    pooled_curved_diagnostics=pool,
                )
            )
        ambiguous = sum(
            r["points"] for r in rows if r["compatible"] and r["feasible_candidates"] > 1
        )
        bound_hits = []
        for n, parameter in parameters.items():
            theta = np.array(parameter["theta"])
            if method == "family_extension":
                if abs(theta[1]) >= 19.8:
                    bound_hits.append(int(n))
            else:
                covariance = np.array(parameter["covariance"])[1:, 1:]
                if theta[1:] @ np.linalg.solve(covariance, theta[1:]) >= 4.99**2:
                    bound_hits.append(int(n))
        audit.append(
            dict(
                method=method,
                arm=arm,
                ambiguous_points=ambiguous,
                unique_frequency_gate_points=len(ids) - ambiguous,
                satellites_at_correction_boundary=bound_hits,
                pooled_curved_passing_families=sum(
                    x["pooled_curved_diagnostics"]["noise_screen_pass"]
                    for x in families
                    if x["method"] == method and x["arm"] == arm and x["pooled_curved_diagnostics"]
                ),
                not_a_calibrated_identity_confidence=True,
            )
        )
        results[method, arm] = association
    pairs = []
    for arm in ("c0", "fitted_c"):
        a, b = [results[m, arm] for m in ("family_extension", "prior_orbit_em")]
        ai, bi = set(a["associated_observation_ids"]), set(b["associated_observation_ids"])
        shared = ai & bi
        alabel = {
            oid: r["candidate_norad"]
            for r in a["rows"]
            if r["compatible"]
            for oid in mapping[r["component"]]["observation_ids"]
        }
        blabel = {
            oid: r["candidate_norad"]
            for r in b["rows"]
            if r["compatible"]
            for oid in mapping[r["component"]]["observation_ids"]
        }
        pairs.append(
            dict(
                arm=arm,
                shared_points=len(shared),
                a_only=len(ai - bi),
                b_only=len(bi - ai),
                jaccard=len(shared) / len(ai | bi),
                agreeing_satellite_labels=sum(alabel[x] == blabel[x] for x in shared),
            )
        )
    for method in ("family_extension", "prior_orbit_em"):
        assert (
            results[method, "c0"]["associated_observation_ids"]
            == results[method, "fitted_c"]["associated_observation_ids"]
        )
    write(OUTPUT / "baseline_control.json", controls)
    write(OUTPUT / "family_diagnostics.json", families)
    write(OUTPUT / "comparison_audit.json", dict(methods=audit, pairwise=pairs))
    fields = [
        "method",
        "arm",
        "associated",
        "percent_associated",
        "unassociated",
        "polynomial_fragments",
        "mean_points_per_fragment",
        "candidate_satellites",
        "gained",
        "lost",
    ]
    with (OUTPUT / "summary.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summaries)
    files = [
        ROOT / "src/leo/analysis/research/shared_satellite_correction.py",
        ROOT / "tools/run_s01_shared_satellite_prototypes.py",
        OUTPUT / "causal_prior_inputs.json",
    ]
    write(
        OUTPUT / "validation.json",
        dict(
            checks_passed=True,
            baseline_original_ids_reproduced=True,
            original_raw_points=4797,
            graph_polynomial_points=4486,
            raw_without_retained_polynomial=311,
            linear_calibration_used=False,
            changed_golden_fixtures=False,
            matched_c_arms_same_point_ids=True,
            inputs_and_sources={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
            },
        ),
    )
    print(json.dumps(dict(methods=audit, pairwise=pairs)), flush=True)


if __name__ == "__main__":
    run()
