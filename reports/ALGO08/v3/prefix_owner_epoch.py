"""Score held pilot arrivals for the two dense alternatives on unchanged observations."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

import numpy as np

from reports.ALGO08.v3.prefix_owner_reach import INPUTS
from tools.pipeline_eval.qualification import range_epoch_model as phase


def pinned(path, digest):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError(f"Unexpected input {path.name}")
    return json.loads(raw)


def split_intervals(times):
    dt = np.diff(times)
    if np.any(dt <= 0):
        raise ValueError("The matched observations must be strictly time ordered")
    cut = times[0] + 2 * (times[-1] - times[0]) / 3
    return (dt <= phase.GAP_S) & (times[1:] < cut), (dt <= phase.GAP_S) & (times[:-1] >= cut)


def score_hypotheses(observed, dt, train, held, models, period):
    from tools.pipeline_eval.variants.code_carrier import predict

    if train.sum() < 4 or held.sum() < 2 or np.any(train & held):
        raise ValueError("Insufficient independent intervals")
    candidates = []
    for shift, expected in models:
        residual = predict(observed, expected, dt[:, None], train, phase.EPOCH_UNIT, period)
        candidates.append((float(np.mean(residual[train]**2)), abs(shift), shift, residual))
    _, _, shift, residual = min(candidates, key=lambda row: row[:3])
    return dict(shift_s=shift, held_rms_samples=float(np.sqrt(np.mean(residual[held]**2))))


def satellite_positions(satellite, utc, shift_s):
    from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns, teme_to_ecef

    jd, fraction = julian_day_from_utc_ns(utc + round(shift_s * 1e9))
    errors, position, velocity = satellite.sgp4_array(jd, fraction)
    if np.any(errors):
        raise ValueError("Unusable SGP4 state in the frozen challenge")
    earth_jd, earth_fraction = julian_day_from_utc_ns(utc)
    angle = greenwich_mean_sidereal_time_rad(earth_jd, earth_fraction)
    return teme_to_ecef(position, velocity, angle)[0]


def compare(documents, binding):
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.frames import geodetic_to_ecef_km
    from tools.pipeline_eval.qualification.paired_publication import archive_identity
    from tools.pipeline_eval.qualification.range_epoch_trial import native_winners

    start = process_time()
    packet = documents["detector"]
    named = []
    for key in ("before", "after"):
        row = documents[key]["selected_rows"]
        if row["c0"] != row["fitted_c"]:
            raise ValueError("Calibrations disagree on the ordered input for this challenge")
        named.append({oid: (norad, role) for oid, norad, role in row["c0"]})
    old, new = named
    swapped = [oid for oid in old.keys() & new.keys() if old[oid] != new[oid]]
    pairs = {(old[oid][0], new[oid][0]) for oid in swapped}
    if len(swapped) != 222 or pairs != {(67511, 63478)}:
        raise ValueError("The frozen competing assignments changed")
    old_id, new_id = next(iter(pairs))
    observed = native_winners(packet)
    groups = defaultdict(list)
    for oid in swapped:
        row = observed[oid]
        groups[row["rx"], row["channel"], row["rf_hz"]].append(row)

    offer = pinned(Path(binding["region"]), binding["offer_sha256"])
    region = SearchRegion(tuple(offer["center"]), offer["width_km"])
    h = region.half_width_km
    sites = [geodetic_to_ecef_km(*region.latlon(xy), 0) for xy in ((0, 0), (-h,-h), (-h,h), (h,-h), (h,h))]
    anchor = packet["clock_anchor"]
    cutoff = anchor["before"]["realtime_ns"]
    origin = (cutoff + anchor["after"]["realtime_ns"]) // 2
    archive = Path(binding["archive"]["root"])
    if cutoff != binding["cutoff_utc_ns"] or archive_identity(archive)["snapshots_sha256"] != binding["archive"]["snapshots_sha256"]:
        raise ValueError("Causal offer or orbit archive differs from the saved solver")
    catalog = causal_catalogue(TleArchiveReader(archive), cutoff).catalogue
    satellites = {i: catalog.satellites[catalog.satellite_numbers.index(i)] for i in (old_id, new_id)}
    prepared = process_time()
    rate = packet["source"]["sample_rate_hz"]
    lanes = []
    for (radio, channel, rf), rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["time_s"])
        times = np.array([row["time_s"] for row in rows])
        train, held = split_intervals(times)
        lane = dict(receiver=radio, channel=channel, rf_hz=rf, observations=len(rows),
                    train=int(train.sum()), held=int(held.sum()), sites=[])
        lanes.append(lane)
        if train.sum() < 4 or held.sum() < 2:
            continue
        utc = origin + np.rint(times * 1e9).astype(np.int64)
        epochs = [row["phase"] for row in rows]
        period = rate / phase.FRAME_HZ
        code = phase.wrap(np.diff(epochs), period)
        dt = np.diff(times)
        clock = score_hypotheses(code, dt, train, held, [(0, np.zeros_like(dt))], period)
        lane["clock_rms_samples"] = clock["held_rms_samples"]
        states = {i: [(shift, satellite_positions(sat, utc, shift)) for shift in (-3, 0, 3)]
                  for i, sat in satellites.items()}
        for site in sites:
            scores = {}
            for number, shifted in states.items():
                for sign, name in ((1, "positive"), (-1, "reflected")):
                    models = [(shift, np.diff(np.linalg.norm(pos - site, axis=1)) * sign * rate / phase.LIGHT_KM_S)
                              for shift, pos in shifted]
                    scores[f"{number}_{name}"] = score_hypotheses(code, dt, train, held, models, period)
            lane["sites"].append(scores)
    winners = []
    passed = []
    for lane in lanes:
        for scores in lane["sites"]:
            positive = {i: scores[f"{i}_positive"]["held_rms_samples"] for i in satellites}
            best = min(positive, key=positive.get)
            winners.append(best)
            controls = [lane["clock_rms_samples"], *(scores[f"{i}_reflected"]["held_rms_samples"] for i in satellites)]
            passed.append(positive[best] < min(controls) and positive[best] < positive[next(i for i in satellites if i != best)])
    return dict(recording="DS30-0008", input_sha256=INPUTS, original=old_id, replacement=new_id, lanes=lanes,
                total_checks=len(passed), passes=sum(passed), winners_agree=len(set(winners)) == 1,
                advance=bool(passed) and all(passed) and len(set(winners)) == 1,
                inputs_and_catalogue_cpu_s=prepared-start, model_and_scores_cpu_s=process_time()-prepared)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for argument in (*INPUTS, "binding"):
        cli.add_argument(argument, type=Path)
    paths = vars(cli.parse_args())
    binding = pinned(paths.pop("binding"), "cfbf388f8bf90f34f8ced8ad6d3d1ca128075b43e528cf7b09684c71ea120070")
    print(json.dumps(compare({key: pinned(path, INPUTS[key]) for key, path in paths.items()}, binding), indent=2, allow_nan=False))
