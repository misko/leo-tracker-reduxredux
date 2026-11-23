"""Cross-check variance information from directionally supported short factors."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import remainder, sqrt
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from aperture_trial import RELEASE, read, write


BLOCK_SAMPLES = 40_000_000
MEDIAN_CHI_SQUARE_ONE = .4549364231
CASES = ("physical", "north")
TRACKS_SHA256 = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
PUBLICATIONS = {
    "physical": Path("/var/tmp/leo-short-graph-20261123-physical"),
    "north": Path("/var/tmp/leo-north-short-regional-nov23/containing"),
}


def mark_observations(native):
    from bidirectional_selection import supported
    from short_primary_epoch_audit import paired_probes

    rows = native["source"]["probes"]
    projected, census = supported(rows)
    start = native["clock_anchor"]["sample_counter"]
    result = {}
    for (oid, probe, _, selected, short), retained in zip(paired_probes(native, native), projected, strict=True):
        if selected is None:
            continue
        block = (probe["valid_start_counter"] - start) // BLOCK_SAMPLES
        result[oid] = dict(block=block, visit=probe["visit_index"], supported=bool(retained["candidates"]), short=short)
    if sum(not line["supported"] for line in result.values()) != census["neither"]:
        raise ValueError("Noise marks do not match the original two-sided selection")
    return result, census


def lane(observation):
    return observation["receiver"], observation["channel"], observation["actual_rf_hz"]


def category(mark):
    return ("short" if mark["short"] else "full") + ("_supported" if mark["supported"] else "_unsupported")


def bracket_forecast(track, time):
    times = track["times"]
    index = int(np.searchsorted(times, time))
    if index < 3 or index+3 > len(times):
        return None
    section = slice(index-3,index+3)
    offsets = times[section]-time
    if not (-8. <= offsets[0] < offsets[2] < 0. < offsets[3] < offsets[-1] <= 8.
            and max(-offsets[2], offsets[3]) <= 3.):
        return None
    values = track["values"][section]
    design = np.vander(offsets, 3, increasing=True)
    coefficients, _, rank, _ = np.linalg.lstsq(design, values - values[0], rcond=None)
    rms = float(np.sqrt(np.mean((values - values[0] - design @ coefficients)**2)))
    if rank != 3 or rms > 450. or abs(coefficients[1]) > 8000.:
        return None
    leverage = float(np.linalg.solve(design.T @ design, np.array([1., 0., 0.]))[0])
    if not np.isfinite(leverage) or leverage < 0.:
        return None
    return dict(frequency_hz=float(coefficients[0]+values[0]), slope_hz_s=float(coefficients[1]),
                training_rms_hz=rms, leverage=leverage,
                donor_ids=track["observation_ids"][section])


def forecasting_noise(metadata, margin):
    if metadata["extra_parameter_BIC_gain"] <= 0.:
        return metadata["constant_radio_sigma_hz"]
    variance = metadata["floor_sigma_hz"]**2 + metadata["strength_hz2"]/margin
    return float(np.sqrt(np.clip(variance, 40.**2, 600.**2)))


def profile(dataset, config):
    from leo.analysis.localization_v3.noise import estimate_noise
    from leo.analysis.localization_v3.tracks import graph_tracks, winning_observations

    start, wall = process_time(), perf_counter()
    marks, census = mark_observations(dataset)
    rows, _ = winning_observations(dataset)
    if {row["observation_id"] for row in rows} != marks.keys():
        raise ValueError("Need the existing unfiltered winning observations")
    forecasts, opportunities, folds = [], defaultdict(Counter), []
    for held in range(2):
        def is_held(row):
            return marks[row["observation_id"]]["block"]%2 == held

        training = [row for row in rows if not is_held(row)]
        tracks, assigned = graph_tracks(training, config)
        noise = estimate_noise(tracks, training)
        active = defaultdict(list)
        for t in tracks:
            active[t["receiver"], t["channel"], t["rf_hz"]].append(t)
        folds.append(dict(parity=held, training_count=len(training), tracks=len(tracks),
                          graph_points=assigned, base_noise={k:v for k,v in noise.items()
                                                     if k!="per_observation_noise_sigma_hz"}))
        for row in rows:
            if not is_held(row):
                continue
            oid = row["observation_id"]
            mark = marks[oid]
            group = category(mark)
            totals = opportunities[group]
            totals["held_factors"] += 1
            if lane(row) not in active:
                totals["no_donor_track_on_lane"] += 1
                continue
            fits = [fit for t in active[lane(row)] if (fit := bracket_forecast(t, row["time_s"])) is not None]
            if len(fits) != 1:
                totals["ambiguous_donor_tracks" if fits else "no_valid_bracket"] += 1
                continue
            fit, = fits
            if any(marks[donor]["block"]%2 == held for donor in fit["donor_ids"]):
                raise ValueError("Held observation leaked into a donor forecast")
            totals["unique_forecasts"] += 1
            delta = row["measured_cfo_hz"]-fit["frequency_hz"]
            innovation = remainder(delta, config.alias_spacing_hz)
            sigma = forecasting_noise(noise, row["fractional_margin"])
            error = innovation/sqrt(1.+fit["leverage"])
            forecasts.append(dict(observation_id=oid, lane=lane(row), **mark, **fit, category=group,
                                  periodic_innovation_hz=innovation, leverage_corrected_error_hz=error,
                                  launch_sigma_hz=sigma, standardized_squared_error=(error/sigma)**2,
                                  time_s=row["time_s"], raw_cfo_hz=row["measured_cfo_hz"]))
    return dict(continuation=census, coverage=dict(opportunities), donor_folds=folds, held=forecasts,
                cpu_s=process_time()-start, elapsed_s=perf_counter()-wall)


def variance_evidence(result):
    by_group = defaultdict(list)
    for row in result["held"]:
        by_group[row["category"]].append(row)
    summaries = {}
    for name in ("short_supported", "short_unsupported", "full_supported", "full_unsupported"):
        rows = by_group[name]
        sq = [row["standardized_squared_error"] for row in rows]
        actual = [abs(row["leverage_corrected_error_hz"]) for row in rows]
        summaries[name] = dict(rows=len(rows), visits=len({row["visit"] for row in rows}),
                               receiver_rf_lanes=len({tuple(row["lane"]) for row in rows}),
                               blocks=len({row["block"] for row in rows}),
                               median_abs_corrected_hz=float(np.median(actual)) if actual else None,
                               periodic_error_over_450_hz=sum(abs(row["periodic_innovation_hz"])>450. for row in rows),
                               periodic_error_over_8000_hz=sum(abs(row["periodic_innovation_hz"])>8000. for row in rows),
                               median_standardized_square=float(np.median(sq)) if sq else None,
                               squared_rms_standardized=float(np.mean(sq)) if sq else None)
    unsupported, supported = (summaries[key] for key in ("short_unsupported", "short_supported"))
    enough = (unsupported["rows"] >= 12 and unsupported["visits"] >= 4
              and unsupported["receiver_rf_lanes"] >= 2 and supported["rows"] >= 24)
    base, new = (item["median_standardized_square"] for item in (supported, unsupported))
    ratio = new/base if base and new is not None else None
    return dict(groups=summaries, coverage_gate=bool(enough),
                descriptive_short_ratio=ratio, calibrated_ratio=ratio if enough and ratio is not None and ratio>1. else None)


def transfer(source, target, summary):
    """Apply a ratio frozen on another recording to target unsupported rows."""
    if source["calibrated_ratio"] is None or not summary["coverage_gate"]:
        return dict(scored=False, reason="independent calibrated ratio or target coverage unavailable")
    scale = summary["groups"]["short_supported"]["median_standardized_square"]/MEDIAN_CHI_SQUARE_ONE
    if not np.isfinite(scale) or scale <= 0.:
        return dict(scored=False, reason="no positive held supported scale")
    risk = [row["standardized_squared_error"]/scale for row in target["held"] if row["category"]=="short_unsupported"]
    ratio = source["calibrated_ratio"]
    changes = np.log(ratio) + np.asarray(risk)*(1./ratio-1.)
    return dict(scored=True, applied_ratio=ratio, held_rows=len(risk),
                held_deviance_change=float(np.mean(changes)), improves=bool(np.mean(changes)<0.))


def load(case):
    from leo.contracts.digests import canonical_digest
    from short_stereo_trial import source_for
    from short_primary_epoch_audit import SHORT

    _, _, _, source, expected, _ = source_for(case)
    document = read(source)
    native = document["source"]
    if (canonical_digest(document) != expected or document["provenance"]["detector_sha256"] != SHORT
            or native["analysis_manifest_sha256"] != canonical_digest([
                "cancellation", native["raw_recording_authority_digest"], SHORT[7:], native["probes"]])):
        raise ValueError("Saved unfiltered short packet or signed receiver binding changed")
    return document, dict(native_sha256=expected, path=str(source), session_id=native["session_id"],
                          raw_authority=native["raw_recording_authority_digest"], detector=SHORT)


def full_slot_brackets(rows, marks):
    full = defaultdict(list)
    for row in rows:
        if not marks[row["observation_id"]]["short"]:
            full[lane(row)].append(row["time_s"])
    totals = defaultdict(Counter)
    for row in rows:
        mark = marks[row["observation_id"]]
        if not mark["short"]:
            continue
        group = totals[category(mark)]
        prior = full[lane(row)]
        t = row["time_s"]
        i = bisect_left(prior, t)
        before = i > 0 and 0. < t-prior[i-1] <= 8.
        following = i < len(prior) and 0. < prior[i]-t <= 8.
        group.update(total=1, before=before, after=following, both=before and following)
    return dict(totals)


def exposure(case, document, binding, config):
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from north_factor_swap import continued
    from short_primary_epoch_audit import paired_probes

    start = process_time()
    marks, _ = mark_observations(document)
    prepared = prepare_tracks(document, config)
    graph = Counter(category(marks[oid]) for track in prepared["tracks"] for oid in track["observation_ids"])
    curved = Counter(category(marks[oid]) for i in prepared["curved_indices"]
                     for oid in prepared["tracks"][i]["observation_ids"])
    root = PUBLICATIONS[case]
    run = read(root / "joint-research-receipt.json")
    seal = run["receipt"]
    terminal = read(root / "fast-scan-automatic-work" / seal["run_id"] / "terminal.json")
    manifest = read(FastStandardAnalysisStore(root).folder(seal["run_id"]) / "manifest.json")
    if (terminal["native_sha256"] != binding["native_sha256"]
            or canonical_digest(terminal) != seal["terminal_sha256"]
            or manifest["terminal_sha256"] != seal["terminal_sha256"] or seal["decision"]!="complete"):
        raise ValueError("Original unfiltered exposure is not sealed to the analysis packet")
    causal = continued(document)
    past = {oid for oid, _, _, chosen, _ in paired_probes(document, causal) if chosen is not None}
    owners, forward_failures = {}, {}
    for arm, assigned in run["selected_rows"].items():
        lookup = {oid: number for oid, number, _ in assigned}
        if (len(lookup) != len(assigned) or owner_digest(lookup) != manifest["arms"][arm]["owner_sha256"]
                or len(lookup) != manifest["arms"][arm]["associated_points"]):
            raise ValueError("Published owner inventory does not match its manifest")
        types = defaultdict(Counter)
        forward_failed = Counter()
        for oid, _, role in assigned:
            types[role][category(marks[oid])] += 1
            if marks[oid]["short"] and oid not in past:
                reason = "future_only" if marks[oid]["supported"] else "neither"
                forward_failed[f"{role}_{reason}"] += 1
        owners[arm] = dict(types)
        forward_failures[arm] = forward_failed
    return dict(full_slots=full_slot_brackets(prepared["observations"], marks),
                graph=dict(points=prepared["graph_points"], tracks=len(prepared["tracks"]), categories=graph,
                           curved_categories=curved), archived_unfiltered_terminal=seal["terminal_sha256"],
                archived_unfiltered=owners, archived_short_forward_failures=forward_failures,
                cpu_s=process_time()-start)


def run():
    from dense_geographic_trial import host
    from leo.analysis.polynomial_tracklets import TrackConfig

    machine = host()
    path = RELEASE / "assets/tracks.json"
    if sha256(path.read_bytes()).hexdigest() != TRACKS_SHA256:
        raise ValueError("Expected installed Graph configuration")
    config = TrackConfig(**read(path)["config"])
    results, summaries = {}, {}
    for case in CASES:
        dataset, binding = load(case)
        results[case] = dict(binding=binding, **profile(dataset, config))
        summaries[case] = variance_evidence(results[case])
        results[case]["availability_only"] = exposure(case, dataset, binding, config)
    comparisons = {target: transfer(summaries[source], results[target], summaries[target])
                   for target, source in zip(CASES, reversed(CASES), strict=True)}
    accepted = all(fit.get("improves", False) for fit in comparisons.values())
    pooled = variance_evidence(dict(held=[row for result in results.values() for row in result["held"]]))
    return dict(calibration_passed=accepted, ratio_for_position=pooled["calibrated_ratio"] if accepted else None,
                independent_transfer=comparisons, cases=results, summaries=summaries, machine=machine,
                installed_graph_config_sha256=TRACKS_SHA256)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write(parser.parse_args().output, run())
