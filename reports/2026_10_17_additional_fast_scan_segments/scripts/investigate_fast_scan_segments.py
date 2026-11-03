"""Bounded saved-model diagnostics for three user-selected fast-scan intervals.

No acquisition, position search, model retraining, or production publication.
Satellite matching below is conditional on the saved whole-scan calibration.
"""

import argparse
import json
import time
from itertools import combinations
from pathlib import Path

import numpy as np

TARGETS = (
    ("RX1 CH3 40–60 s", 3, 40, 60),
    ("RX1 CH2 110–140 s", 2, 110, 140),
    ("RX1 CH4 250–280 s", 4, 250, 280),
)


def coherent_rows(times, frequencies, tolerance_hz=500):
    """Orbit-blind circular quadratic consensus; retain every excluded ID."""
    from leo.analysis.regional_position_score import circular

    best = np.ones(len(times), bool)
    if len(times) < 3:
        return best
    count, loss = 0, float("inf")
    for indices in combinations(range(len(times)), 3):
        selected = np.asarray(indices)
        if np.min(np.diff(times[selected])) < 2:
            continue
        dt = times - times[selected[1]]
        values = circular(frequencies - frequencies[selected[1]])
        coefficients = np.polyfit(dt[selected], values[selected], 2)
        if abs(coefficients[1]) > 4000 or abs(coefficients[0]) > 30:
            continue
        residual = circular(values - np.polyval(coefficients, dt))
        keep = abs(residual) <= tolerance_hz
        score = int(keep.sum())
        rms = float(np.mean(residual[keep] ** 2))
        if (score, -rms) > (count, -loss):
            best, count, loss = keep, score, rms
    return best


def grouped_folds(times, seed=20261016):
    groups = np.floor(np.asarray(times) / 2).astype(int)
    unique = np.unique(groups)
    np.random.default_rng(seed).shuffle(unique)
    assignment = {int(group): i % 5 for i, group in enumerate(unique)}
    return np.asarray([assignment[int(group)] for group in groups])


def search_candidates(predictions, visibility, measured, grid, train, *, allow_offset):
    """Training data alone selects satellite, timing and optional offset."""
    from leo.analysis.regional_position_score import circular

    residual = circular(measured[None, :, None] - predictions)
    offset = (
        np.mean(residual[:, train], axis=1)
        if allow_offset
        else np.zeros((len(grid), predictions.shape[2]))
    )
    error = circular(residual - offset[:, None, :])
    score = np.sum((error[:, train] / 125) ** 2, axis=1)
    score += (grid[:, None] / 2) ** 2 + (offset / 4000) ** 2
    score[~visibility[:, train].all(axis=1)] = np.inf
    score[abs(offset) > 10000] = np.inf
    by_satellite = score.min(axis=0)
    ranked = np.argsort(by_satellite)[:5]
    result = []
    for satellite in ranked:
        g = int(score[:, satellite].argmin())
        result.append(
            dict(
                index=int(satellite),
                timing_s=float(grid[g]),
                offset_hz=float(offset[g, satellite]),
                score=float(score[g, satellite]),
                train_rms_hz=float(np.sqrt(np.mean(error[g, train, satellite] ** 2))),
                test_rms_hz=float(np.sqrt(np.mean(error[g, ~train, satellite] ** 2)))
                if np.any(~train)
                else None,
            )
        )
    return result


def main():
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_bootstrap import observation_subset
    from leo.analysis.regional_position_score import circular, zero_sum_basis
    from leo.application.shared_fast_position import prepare_views
    from leo.application.shared_orbit_replay import selected_model
    from leo.cli.shared_fast_position import load_input
    from leo.contracts.regional_position import RegionalPrior
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    from leo.storage.shared_fast_scan import SharedFastScanStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    store = SharedFastScanStore("/srv/bulk/leo", "shared-scan-q-v2")
    job, document, terminal, stages = store.plot_evidence("075b34f9532dd9f7caf6c70830e4e8e8")
    source = load_input(document)
    prepared, nodes = prepare_views(source)
    obs = prepared["all"].observations
    prior = RegionalPrior(**terminal["provenance"]["prior"])
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = next(
        s for s in archive.list_snapshots() if s.digest == terminal["provenance"]["tle_sha256"]
    )
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    cat = parse_element_sets(payload)
    lookup = {int(n): i for i, n in enumerate(cat.satellite_numbers)}
    numbers = terminal["candidate_numbers"]
    bank, _ = build_regional_bank(
        cat,
        [lookup[n] for n in numbers],
        prepared["all"].start_utc_ns,
        obs,
        prior,
        maximum_seconds=60,
    )
    bank = bank.select([list(bank.numbers).index(n) for n in numbers])
    model, fit, audit = selected_model(prepared, bank, prior, nodes, terminal, stages)
    vector, nuisance = np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
    correction = model.original.correction(vector, nuisance[: model.clock_count])
    terms = model.evaluate_joint(vector, nuisance)[3]
    best = terms.responsibilities.argmax(axis=1)
    associated = terms.responsibilities[np.arange(len(best)), best] > terms.clutter_probability
    shifts = vector[7] + zero_sum_basis(len(numbers)) @ vector[8:]
    calibrated = obs.measured_hz - correction
    targets = []
    for label, channel, low, high in TARGETS:
        rows = np.flatnonzero(
            (obs.receiver == 0)
            & (obs.channel == channel)
            & (obs.times_s >= low)
            & (obs.times_s <= high)
        )
        loose = rows[~associated[rows]]
        coherent = rows[coherent_rows(obs.times_s[rows], calibrated[rows])]
        target = dict(
            label=label,
            channel=channel,
            interval_s=[low, high],
            interval_rows=rows.tolist(),
            unassociated_rows=loose.tolist(),
            coherent_rows=coherent.tolist(),
            interval_count=len(rows),
            unassociated_count=len(loose),
            coherent_count=len(coherent),
            baseline_assignments={
                str(n): int(np.sum(associated[rows] & (best[rows] == j)))
                for j, n in enumerate(numbers)
                if np.any(associated[rows] & (best[rows] == j))
            },
        )
        targets.append(target)
        print(json.dumps(target), flush=True)
    full_numbers = terminal["provenance"]["full_candidate_numbers"]
    full, _ = build_regional_bank(
        cat,
        [lookup[n] for n in full_numbers],
        prepared["all"].start_utc_ns,
        obs,
        prior,
        maximum_seconds=60,
    )
    full = full.select([list(full.numbers).index(n) for n in full_numbers])
    grid = np.linspace(-5, 5, 201)
    zero_vector = vector.copy()
    zero_vector[6] = 0
    zero_correction = model.original.correction(zero_vector, nuisance[: model.clock_count])
    for target in targets:
        rows = np.asarray(target["coherent_rows"], int)
        sub = observation_subset(obs, rows)
        predictions, visibility = [], []
        for shift in grid:
            values, visible, _, _ = predict_orbits(
                full, sub, prior, vector[:2], np.full(len(full.numbers), shift), derivatives=False
            )
            predictions.append(values)
            visibility.append(visible)
        predictions, visibility = np.asarray(predictions), np.asarray(visibility)
        folds = grouped_folds(sub.times_s)
        target["fold_ids"] = folds.tolist()
        target["window_ids"] = [obs.window_ids[i] for i in rows]
        target["searches"] = []
        for arm, corr in (("fitted-c", correction), ("zero-c-frozen-other-terms", zero_correction)):
            measured = obs.measured_hz[rows] - corr[rows]
            for allow_offset in (False, True):
                entry = dict(
                    arm=arm, family="timing+offset" if allow_offset else "timing", folds=[]
                )
                for fold in (-1, 0, 1, 2, 3, 4):
                    train = np.ones(len(rows), bool) if fold == -1 else folds != fold
                    ranked = search_candidates(
                        predictions, visibility, measured, grid, train, allow_offset=allow_offset
                    )
                    for r in ranked:
                        r["satellite"] = int(full.numbers[r.pop("index")])
                        r["in_production_selection"] = r["satellite"] in numbers
                    entry["folds"].append(
                        dict(
                            fold=fold,
                            train_count=int(train.sum()),
                            test_count=int((~train).sum()),
                            ranked=ranked,
                        )
                    )
                target["searches"].append(entry)
                print(
                    json.dumps(
                        dict(
                            label=target["label"],
                            arm=arm,
                            family=entry["family"],
                            best=entry["folds"][0]["ranked"][:2],
                            cv=[f["ranked"][0] for f in entry["folds"][1:]],
                        )
                    ),
                    flush=True,
                )
        (args.output / "targets-progress.json").write_text(json.dumps(targets, indent=2) + "\n")
    np.savez_compressed(
        args.output / "baseline.npz",
        times_s=obs.times_s,
        measured_hz=obs.measured_hz,
        correction_hz=correction,
        calibrated_hz=calibrated,
        receiver=obs.receiver,
        channel=obs.channel,
        margin=obs.margin,
        associated=associated,
        best=best,
        numbers=numbers,
        vector=vector,
        shifts_s=shifts,
    )
    for target in targets:
        rows = np.asarray(target["coherent_rows"], int)
        top = target["searches"][0]["folds"][0]["ranked"][0]
        satellite = top["satellite"]
        one = full.select([list(full.numbers).index(satellite)])
        times_to_test = {"target-timing": top["timing_s"]}
        if satellite in numbers:
            times_to_test["published-timing"] = float(shifts[numbers.index(satellite)])
        target["support_audit"] = []
        for name, shift in times_to_test.items():
            values, visible, _, _ = predict_orbits(
                one, obs, prior, vector[:2], np.array([shift]), derivatives=False
            )
            error = circular(calibrated - values[:, 0])
            groups = {"requested coherent track": np.isin(np.arange(len(best)), rows)}
            if satellite in numbers:
                peers = associated & (best == numbers.index(satellite))
                for receiver in (0, 1):
                    for band, band_mask in (
                        ("CH1–4", obs.channel <= 4),
                        ("CH5–8", obs.channel >= 5),
                    ):
                        groups[f"published associations RX{receiver + 1} {band}"] = (
                            peers & (obs.receiver == receiver) & band_mask
                        )
            for label, mask in groups.items():
                indices = np.flatnonzero(mask)
                if len(indices):
                    target["support_audit"].append(
                        dict(
                            timing=name,
                            shift_s=shift,
                            group=label,
                            count=len(indices),
                            rms_hz=float(np.sqrt(np.mean(error[indices] ** 2))),
                            median_residual_hz=float(np.median(error[indices])),
                            times_s=obs.times_s[indices].tolist(),
                            rows=indices.tolist(),
                        )
                    )
            # A counterpart compatibility check, not an RX2 acquisition claim.
            mask = (obs.receiver == 1) & (obs.channel == target["channel"])
            mask &= (obs.times_s >= target["interval_s"][0]) & (
                obs.times_s <= target["interval_s"][1]
            )
            idx = np.flatnonzero(mask & visible[:, 0])
            target.setdefault("rx2_compatibility", []).append(
                dict(
                    timing=name,
                    windows=len(idx),
                    within_375_hz=int(np.sum(abs(error[idx]) <= 375)),
                    compatible_rows=idx[abs(error[idx]) <= 375].tolist(),
                )
            )

    from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource

    winners = {}
    for point in project_scanner_candidates(source):
        old = winners.get(point.source_group_id)
        if old is None or (-point.margin, point.candidate_rank, point.candidate_id) < (
            -old.margin,
            old.candidate_rank,
            old.candidate_id,
        ):
            winners[point.source_group_id] = point
    points = sorted(winners.values(), key=lambda p: (p.support_center_utc_ns, p.source_group_id))
    assert [p.source_group_id for p in points] == list(obs.window_ids)
    wanted = {}
    for target in targets:
        rows = np.asarray(target["coherent_rows"], int)
        for i in rows[[0, len(rows) // 2, -1]]:
            wanted[points[i].visit_index] = (int(i), target["label"])
    inventory = FastScanStore("/srv/bulk/leo").source(
        source.session_id, source.input_manifest_sha256
    )
    probes = {(p.visit_index, p.receiver_id, p.probe_index): p for p in source.probes}
    raw = []
    base = 0
    replay_start = time.monotonic()
    for entry in inventory["segments"]:
        visits = set(range(base, base + entry["windows"])) & set(wanted)
        base += entry["windows"]
        if not visits:
            continue
        reader = FastSegmentSource(entry)
        for window in reader.windows():
            if time.monotonic() - replay_start > 120:
                raise TimeoutError("Nine-probe replay exceeded 120 seconds")
            visit = window.acquisition["global_visit"]
            if visit not in visits:
                continue
            i, label = wanted[visit]
            point = points[i]
            probe = probes[(visit, point.receiver_id, point.probe_index)]
            assert window.acquisition["sample_start"] == probe.valid_start_counter
            candidate = next(
                c for c in probe.candidates if c.candidate_rank == point.candidate_rank
            )
            iq = window.samples[:, list(reader.receiver_ids).index(0), :].astype(float)
            score, _ = continuous_glrt_score(
                iq[:, 0] + 1j * iq[:, 1],
                source.sample_rate_hz,
                anchor=candidate.integer_epoch_sample,
                offset=candidate.fractional_epoch_offset_samples,
                conditioning_cfo_hz=candidate.fractional_tracking_cfo_hz,
                edge=probe.edge,
            )
            raw.append(
                dict(
                    label=label,
                    row=i,
                    visit=visit,
                    time_s=float(obs.times_s[i]),
                    iq_sha256=window.iq_sha256,
                    stored_cfo_hz=candidate.fractional_tracking_cfo_hz,
                    continuous_cfo_hz=score.tracking_cfo_hz,
                    change_hz=float(
                        circular(score.tracking_cfo_hz - candidate.fractional_tracking_cfo_hz)
                    ),
                    stored_margin=candidate.fractional_margin,
                    continuous_margin=score.margin,
                )
            )
            print(json.dumps(raw[-1]), flush=True)
            if all(any(r["visit"] == v for r in raw) for v in visits):
                break
    assert len(raw) == 9
    (args.output / "raw-replay.json").write_text(json.dumps(raw, indent=2) + "\n")
    result = dict(
        recording="fast8-auto-20261016-223211-029a4eef-1-lower",
        run_id=job["run_id"],
        input_sha256=job["input_sha256"],
        terminal_sha256=job["terminal"]["sha256"],
        snapshot_sha256=snapshot.digest,
        snapshot_provider=snapshot.provider,
        selected_position=terminal["position"],
        frozen_model_audit=audit,
        total_observations=len(best),
        baseline_associated=int(associated.sum()),
        selected_satellites=numbers,
        full_candidate_numbers=terminal["provenance"]["full_candidate_numbers"],
        targets=targets,
        raw_replay=raw,
        elapsed_s=time.monotonic() - started,
    )
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(15, 10), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(3, 1)
    for target, axis in zip(targets, axes, strict=True):
        rows = np.asarray(target["interval_rows"], int)
        mask = (obs.receiver == 0) & (obs.channel == target["channel"])
        axis.scatter(
            obs.times_s[mask],
            circular(calibrated[mask]) / 1000,
            color="0.7",
            s=6,
            label="All passing top-one windows",
        )
        loose = np.asarray(target["unassociated_rows"], int)
        coherent = np.asarray(target["coherent_rows"], int)
        axis.scatter(
            obs.times_s[loose],
            circular(calibrated[loose]) / 1000,
            color="black",
            s=15,
            label="Unassociated in requested interval",
        )
        axis.scatter(
            obs.times_s[coherent],
            circular(calibrated[coherent]) / 1000,
            facecolors="none",
            edgecolors="red",
            s=45,
            label="Orbit-blind coherent subset",
        )
        for j, _number in enumerate(numbers):
            allrows = np.flatnonzero(mask)
            sub = observation_subset(obs, allrows)
            curves, visible, _, _ = predict_orbits(
                bank.select([j]), sub, prior, vector[:2], shifts[j : j + 1], derivatives=False
            )
            values = circular(curves[:, 0]) / 1000
            values[~visible[:, 0]] = np.nan
            values[np.r_[False, abs(np.diff(values)) > 100]] = np.nan
            axis.plot(sub.times_s, values, lw=0.6, alpha=0.3)
        fitted = target["searches"][0]["folds"][0]["ranked"][0]
        satellite = fitted["satellite"]
        one = full.select([list(full.numbers).index(satellite)])
        allrows = np.flatnonzero(mask)
        sub = observation_subset(obs, allrows)
        values = predict_orbits(
            one, sub, prior, vector[:2], np.array([fitted["timing_s"]]), derivatives=False
        )[0][:, 0]
        values = circular(values) / 1000
        values[np.r_[False, abs(np.diff(values)) > 100]] = np.nan
        axis.plot(
            sub.times_s,
            values,
            color="#0057b8",
            lw=1.7,
            label=f"{satellite} · target timing {fitted['timing_s']:+.2f} s",
        )
        axis.legend(fontsize=8, loc="best")
        axis.set(
            xlim=(max(0, target["interval_s"][0] - 5), min(300, target["interval_s"][1] + 5)),
            ylim=(-114, 114),
            title=target["label"],
            ylabel="Calibrated wrapped CFO (kHz)",
        )
        axis.grid(alpha=0.2)
    axes[-1].set_xlabel("Receive time since scan origin (s)")
    figure.suptitle(
        "Requested segments · saved baseline and conditional target matches\n"
        "Faint: published selected satellites · blue: best full-bank timing-only match"
    )
    figure.savefig(args.output / "candidate-matches.png", dpi=150)


if __name__ == "__main__":
    main()
