"""Causal same-provider TLE update consistency, independent of radio fitting."""

import argparse
import hashlib
import inspect
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOOKBACK_HOURS = (0, 1, 3, 6, 12, 24, 48, 72, 120, 168, 336, 720)
AGE_EDGES_DAYS = (0, .25, .5, 1, 2, 4, 8, 16, 32, float('inf'))
MAXIMUM_OBJECTS = 1024


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_snapshots(snapshots, cutoff):
    eligible = sorted((s for s in snapshots if s.collected_utc_ns < cutoff),
                      key=lambda s: (s.collected_utc_ns, s.digest))
    if not eligible:
        return []
    latest = eligible[-1].collected_utc_ns
    selected = {}
    for hours in LOOKBACK_HOURS:
        earlier = [s for s in eligible if s.collected_utc_ns <= latest-hours*3600*10**9]
        if earlier:
            item = earlier[-1]
            selected.setdefault(item.digest, item)
    return sorted(selected.values(), key=lambda s: s.collected_utc_ns)


def starlink_indices(catalogue):
    return {int(number): i for i, (name, number) in enumerate(zip(
        catalogue.names, catalogue.satellite_numbers, strict=True))
        if name.strip().removeprefix('0 ').upper().startswith('STARLINK-')}


def uniform_numbers(numbers, maximum=MAXIMUM_OBJECTS):
    ordered = sorted(set(numbers))
    if len(ordered) <= maximum:
        return ordered
    return [ordered[i] for i in np.linspace(0, len(ordered)-1, maximum, dtype=int)]


def decompose(old_position, new_position, new_velocity):
    delta = np.asarray(old_position)-np.asarray(new_position)
    velocity = np.asarray(new_velocity)
    speed2 = np.sum(velocity*velocity, axis=-1)
    if np.any(speed2 <= 0) or not np.isfinite(np.r_[delta.ravel(), velocity.ravel()]).all():
        raise ValueError('finite positions and nonzero reference velocity required')
    effective = np.sum(delta*velocity, axis=-1)/speed2
    perpendicular = delta-effective[..., None]*velocity
    return effective, np.linalg.norm(perpendicular, axis=-1), np.linalg.norm(delta, axis=-1)


def summary(rows):
    if not rows:
        return dict(count=0)
    values = np.array([r['effective_along_track_s'] for r in rows])
    perpendicular = np.array([r['perpendicular_km'] for r in rows])
    median = float(np.median(values))
    return dict(count=len(rows), distinct_objects=len({r['number'] for r in rows}),
        median_s=median, mad_sigma_s=float(1.4826*np.median(abs(values-median))),
        absolute_s_quantiles=np.quantile(abs(values), [.5, .9, .95, .99, 1]).tolist(),
        centered_absolute_s_quantiles=np.quantile(abs(values-median),
                                                  [.5, .9, .95, .99, 1]).tolist(),
        perpendicular_km_quantiles=np.quantile(perpendicular, [.5, .9, .95, .99, 1]).tolist(),
        diagnostic_perpendicular_above_1km=int(np.sum(perpendicular > 1.)),
        diagnostic_abs_along_above_1s=int(np.sum(abs(values) > 1.)))


def propagation_times():
    """Public propagation port requires >=3 instants; exact last epoch is used."""
    return np.array([-.002, -.001, 0.])


def run(cutoff):
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    begun = time.monotonic()
    paths = [Path(__file__), HERE/'test_calibrate_v2.py', HERE/'CALIBRATION_PROTOCOL.md',
             HERE/'calibration_v1_failure.json']
    paths += [Path(inspect.getsourcefile(port)) for port in
              (propagate_candidate_states, TleArchiveReader, parse_element_sets)]
    sources = {str(p): digest(p) for p in paths}
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    chosen = {provider: select_snapshots(archive.list_snapshots(provider), cutoff)
              for provider in ('space-track', 'huggingface')}
    authority = {provider: [dict(digest=s.digest, collected_utc_ns=s.collected_utc_ns,
        byte_size=s.byte_size) for s in snapshots] for provider, snapshots in chosen.items()}
    with (HERE/'calibration_v2_launch.json').open('x') as stream:
        json.dump(dict(source_sha256=sources, cutoff_utc_ns=cutoff, snapshots=authority,
            lookback_hours=LOOKBACK_HOURS, maximum_objects_per_pair=MAXIMUM_OBJECTS,
            selection='same-provider latest causal reference; common STARLINK names; '
                      'uniform catalogue-number sample; no target IDs or radio/location data',
            independent_reference=False, localization_fits=0), stream, indent=2)
    pairs = []
    for provider, snapshots in chosen.items():
        if len(snapshots) < 2:
            continue
        reference = snapshots[-1]
        newer = parse_element_sets(archive.read(reference))
        nlookup, nepochs = starlink_indices(newer), newer.element_epoch_utc_ns()
        for old_snapshot in snapshots[:-1]:
            if time.monotonic()-begun > 100:
                raise TimeoutError('100-second internal calibration deadline')
            older = parse_element_sets(archive.read(old_snapshot))
            olookup, oepochs = starlink_indices(older), older.element_epoch_utc_ns()
            common = sorted(set(olookup) & set(nlookup))
            unchanged = sum(oepochs[olookup[n]] == nepochs[nlookup[n]] for n in common)
            reversed_epochs = sum(oepochs[olookup[n]] > nepochs[nlookup[n]] for n in common)
            changed = [n for n in common if oepochs[olookup[n]] < nepochs[nlookup[n]]]
            numbers = uniform_numbers(changed)
            oi, ni = [olookup[n] for n in numbers], [nlookup[n] for n in numbers]
            op, _, ov = propagate_candidate_states(older, oi, reference.collected_utc_ns,
                                                   propagation_times(), np.array([0.]))
            np_, nv, valid_new = propagate_candidate_states(newer, ni,
                reference.collected_utc_ns, propagation_times(), np.array([0.]))
            old_valid = {int(i): p[0, -1] for i, p in zip(ov, op, strict=True)}
            new_valid = {int(i): (p[0, -1], v[0, -1])
                for i, p, v in zip(valid_new, np_, nv, strict=True)}
            rows = []
            for number in numbers:
                o, n = olookup[number], nlookup[number]
                if o not in old_valid or n not in new_valid:
                    continue
                dt, perpendicular, displacement = decompose(old_valid[o], *new_valid[n])
                rows.append(dict(number=number, name=newer.names[n], old_epoch_utc_ns=oepochs[o],
                    new_epoch_utc_ns=nepochs[n],
                    old_element_age_days=(reference.collected_utc_ns-oepochs[o])/86400e9,
                    new_element_age_days=(reference.collected_utc_ns-nepochs[n])/86400e9,
                    effective_along_track_s=float(dt), perpendicular_km=float(perpendicular),
                    total_displacement_km=float(displacement)))
            pairs.append(dict(provider=provider, old_digest=old_snapshot.digest,
                new_digest=reference.digest, old_collected_utc_ns=old_snapshot.collected_utc_ns,
                new_collected_utc_ns=reference.collected_utc_ns,
                reference_utc_ns=reference.collected_utc_ns,
                common_starlink=len(common), unchanged_epoch=unchanged,
                reversed_epoch=reversed_epochs, updated_eligible=len(changed), sampled=len(numbers),
                invalid_old=len(numbers)-len(old_valid), invalid_new=len(numbers)-len(new_valid),
                jointly_valid=len(rows), rows=rows, summary=summary(rows)))
            print(provider, old_snapshot.digest[:16], 'valid', len(rows), flush=True)
    bins = []
    for provider in chosen:
        records = [r for p in pairs if p['provider'] == provider for r in p['rows']]
        for lower, upper in zip(AGE_EDGES_DAYS[:-1], AGE_EDGES_DAYS[1:], strict=True):
            use = [r for r in records if lower <= r['old_element_age_days'] < upper]
            bins.append(dict(provider=provider, lower_age_days=lower,
                upper_age_days=upper if np.isfinite(upper) else None, **summary(use)))
    if any(digest(p) != expected for p, expected in sources.items()):
        raise ValueError('calibration source changed')
    with (HERE/'calibration_v2.json').open('x') as stream:
        json.dump(dict(cutoff_utc_ns=cutoff, source_sha256=sources, snapshots=authority,
            pairs=pairs, age_bins=bins, elapsed_seconds=time.monotonic()-begun,
            orbital_propagator_calls=2*len(pairs), localization_fits=0,
            propagation_times_s=propagation_times().tolist(),
            reference_index=-1, v1_failure_preserved=True,
            sign='old position minus newer-reference position, projected on newer ECEF velocity',
            limitation='correlated newer TLE reference is not truth; update differences include '
                       'maneuvers, reference errors and unmodelled directions'), stream, indent=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cutoff-utc-ns', type=int, required=True)
    args = parser.parse_args()
    run(args.cutoff_utc_ns)
