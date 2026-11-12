"""Count potential duplicate saved annotation training recipes without fitting."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import fingerprint

from leo.analysis.localization_v3.recovery_partitions import partition_schedule, planned_split
from leo.contracts.digests import canonical_digest
from leo.storage.localization_v3 import LocalizationV3Store
from leo.storage.localization_v4 import LocalizationV4Store

ARMS = ('c0', 'fitted_c')
FIT_RECIPE = dict(start=np.zeros(2), reference='zeros_like_prior_means', rounds=5,
                  position_steps=48, events=[], predictive=False, reference_limit_s=15.0,
                  orbital_policy=None, target_family=None, fixed_noise_hz=150.0,
                  support_policy='nominal', record_optimizer=False)


class BindingMismatch(ValueError):
    pass


def member_layout(tracks, node, original_mask):
    """Reproduce FixedFamilies row order before applying the retained mask."""
    lookup = {t['key']: i for i, t in enumerate(tracks)}
    if len(lookup) != len(tracks):
        raise ValueError('Prepared track keys must be unique')
    members = [lookup[r['component']] for r in node['seed']['rows'] if r['active_curvature']]
    if not members or len(set(members)) != len(members):
        raise ValueError('Nonempty unique active-curvature members required')
    times = np.concatenate([np.asarray(tracks[i]['times']) for i in members])
    ids = [oid for i in members for oid in tracks[i]['observation_ids']]
    keep = np.asarray(original_mask, dtype=bool)
    if keep.ndim != 1 or len(keep) != len(times) or len(ids) != len(times):
        raise ValueError('Original mask does not match ordered calibration members')
    return members, times, ids, keep


def target_view(tracks, inventory, target, members, member_ids, original_mask, entries):
    """Reproduce original target lookup and inactive-fragment append selection."""
    source = next(r for r in inventory['tracks']
                  if r['track_id'] == target['track_id'] and r['current_large'])
    index = source['track_index']
    track = tracks[index]
    times = np.asarray(track['times'])
    if len(times) != len(track['observation_ids']):
        raise ValueError('Target timestamps and observation IDs differ in length')
    if not target['inactive_fragment']:
        offset = 0
        for i in members:
            end = offset + len(tracks[i]['times'])
            if i == index and original_mask[offset:end].any():
                raise ValueError('Predictive target has active calibration observations')
            offset = end
        return times, None
    occupied = {oid for arm in ARMS
                for oid in inventory['policy'][arm]['proposed_associated_ids']}
    occupied.update(oid for oid, use in zip(member_ids, original_mask, strict=True) if use)
    occupied.update(oid for entry in entries for oid in entry['observation_ids'])
    ids = track['observation_ids']
    if len(ids) != len(set(ids)):
        raise ValueError('Parent graph repeats observation IDs')
    use = np.array([oid not in occupied for oid in ids], bool)
    if not use.any() or use.all():
        raise ValueError('Inactive fragment must contain owned and unowned observations')
    times, values = times[use], np.asarray(track['values'])[use]
    if np.any(np.diff(times) <= 0) or not np.isfinite(np.r_[times, values]).all():
        raise ValueError('Fragment requires finite increasing measurements')
    fragment = dict(parent_track_index=index, appended_track_index=len(tracks),
                    track_id=target['track_id'], component=track['key'] + '-INACTIVE',
                    observation_ids=[oid for oid, k in zip(ids, use, strict=True) if k],
                    source_parent_indices=np.flatnonzero(use), times=times, values=values)
    return times, fragment


def recipe_key(context_sha256, arm, keep):
    return fingerprint(dict(context_sha256=context_sha256, arm=arm,
                            keep=np.asarray(keep, bool), fit_recipe=FIT_RECIPE))


def summarize(rows):
    keys = Counter(r['recipe_sha256'] for r in rows)
    mask_keys = Counter(r['calibration_mask_only_sha256'] for r in rows)
    return dict(potential_calls=len(rows), distinct_recipes=len(keys),
                potential_redundant_calls=len(rows) - len(keys),
                duplicate_recipe_groups=sum(n > 1 for n in keys.values()),
                calibration_mask_only_distinct=len(mask_keys),
                calibration_mask_only_redundant_upper_bound=len(rows) - len(mask_keys),
                executed_proven_hits=None)


def census_evidence(evidence):
    preparation = evidence['preparation']
    cavity = evidence['audit']['cavity_policy']
    if cavity['status'] != 'complete':
        raise ValueError('Complete cavity decision required')
    chosen = cavity['selected'] if cavity['accepted'] else None
    node = chosen['node'] if chosen else cavity['baseline_node']
    entries = chosen['entries'] if chosen else cavity['baseline_entries']
    means = chosen['means'] if chosen else cavity['baseline_means']
    tracks = preparation['tracks']['tracks']
    members, times, ids, original = member_layout(tracks, node, cavity['original_mask'])
    inventory_evidence = evidence['audit']['recovery_inventory']
    inventory = inventory_evidence['inventory']
    context = dict(preparation=preparation, node=node, entries=entries, means=means,
                   model=cavity['model'], original_mask=original, member_indices=members,
                   unit_powers=np.ones(len(cavity['powers'])),
                   provenance=evidence['provenance'])
    base_sha = fingerprint(context)
    rows, targets = [], []
    for target in inventory_evidence['selected_targets']:
        focus, fragment = target_view(tracks, inventory, target, members, ids, original, entries)
        context_sha = (base_sha if fragment is None else
                       fingerprint(dict(original_context=base_sha, appended_fragment=fragment)))
        full_times = np.r_[times, focus]
        seeds, plan = partition_schedule(full_times, focus, shifted_origin=True)
        folds = []
        for seed in seeds[:3]:
            train, held, _ = planned_split(full_times, focus, seed, plan)
            train, held = np.asarray(train, bool), np.asarray(held, bool)
            if train.shape != full_times.shape or held.shape != full_times.shape:
                raise ValueError('Partition masks do not match the full timestamp vector')
            n = len(times)
            eligible = bool(train[n:].sum() >= 8 and held[n:].sum() >= 4)
            fold = dict(seed=int(seed),
                        status='eligible' if eligible else 'insufficient_group_support',
                        target_training_points=int(train[n:].sum()),
                        target_held_points=int(held[n:].sum()))
            if eligible:
                keep = original & train[:n]
                fold.update(calibration_points=int(keep.sum()), keep_sha256=fingerprint(keep))
                for arm in ARMS:
                    rows.append(dict(track_id=target['track_id'], seed=int(seed), arm=arm,
                                     context_sha256=context_sha, keep_sha256=fingerprint(keep),
                                     recipe_sha256=recipe_key(context_sha, arm, keep),
                                     calibration_mask_only_sha256=recipe_key(base_sha, arm, keep)))
            folds.append(fold)
        targets.append(dict(track_id=target['track_id'], inactive_fragment=fragment is not None,
                            target_timestamps_sha256=fingerprint(focus),
                            target_points=len(focus), context_sha256=context_sha,
                            fragment_observation_ids=(fragment['observation_ids']
                                                      if fragment is not None else None),
                            planned_seeds=[int(s) for s in seeds[:3]], folds=folds,
                            geometry_only_early_exit=bool(plan['geometry_only_early_exit'])))
    return dict(status='complete', original_context_sha256=base_sha,
                member_indices=members, original_mask_sha256=fingerprint(original),
                calibration_points=len(times), targets=targets, recipes=rows,
                counts=summarize(rows),
                counts_by_arm={arm: summarize([r for r in rows if r['arm'] == arm])
                               for arm in ARMS})


def census_request(path):
    raw = path.read_bytes()
    request = json.loads(raw)
    wrapped = 'job' in request
    if wrapped and request.get('algorithm') != 'algo07v4-native-v1':
        raise BindingMismatch('Unsupported wrapped request algorithm')
    job = request['job'] if wrapped else request
    root = Path(job['output_root']).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    store = LocalizationV4Store if wrapped else LocalizationV3Store
    saved = store(root).load(job['identity']['run_id'])
    evidence, receipt = saved['evidence'], saved['receipt']
    provenance = evidence['provenance']
    if (provenance['request_sha256'] != canonical_digest(request)
            or provenance['configuration']['request'] != job
            or evidence['identity'] != job['identity']
            or any(receipt[k] != v for k, v in job['identity'].items())
            or saved['sha256'] != canonical_digest(receipt)):
        raise BindingMismatch('Saved evidence/request/receipt binding mismatch')
    return dict(census_evidence(evidence), request_path=str(path),
                request_file_sha256='sha256:' + hashlib.sha256(raw).hexdigest(),
                request_sha256=canonical_digest(request), output_root=str(root),
                identity=job['identity'], receipt=receipt, receipt_sha256=saved['sha256'],
                archive_sha256=receipt['result_sha256'], archive_bytes=receipt['result_bytes'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, action='append', default=[])
    parser.add_argument('--pilot-ledger', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01'):
        parser.error('Output must be local')
    paths = list(args.request)
    bindings = {str(Path(__file__).resolve()):
                'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                str(Path(__file__).with_name('census_algo07v5_initial_controls.py').resolve()):
                'sha256:' + hashlib.sha256(Path(__file__).with_name(
                    'census_algo07v5_initial_controls.py').read_bytes()).hexdigest()}
    if args.pilot_ledger:
        raw = args.pilot_ledger.read_bytes()
        ledger = json.loads(raw)
        bindings[str(args.pilot_ledger.resolve())] = 'sha256:' + hashlib.sha256(raw).hexdigest()
        baseline = [r for r in ledger['runs'] if r['config'] == 'baseline']
        if len(baseline) != 8 or len({r['case'] for r in baseline}) != 8:
            parser.error('Pilot ledger must contain eight distinct baseline cases')
        paths.extend(Path(r['output']) / 'request.json' for r in baseline)
    if not paths:
        parser.error('At least one request or pilot ledger required')
    results = []
    for path in dict.fromkeys(p.resolve() for p in paths):
        try:
            bindings[str(path)] = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
            results.append(census_request(path))
        except (OSError, KeyError, IndexError, TypeError, StopIteration) as exc:
            results.append(dict(request_path=str(path), status='missing', error=str(exc)))
        except ValueError as exc:
            results.append(dict(request_path=str(path), status='mismatching', error=str(exc)))
    counts = {s: sum(r['status'] == s for r in results)
              for s in ('complete', 'mismatching', 'missing')}
    report = dict(schema_version=1, kind='algo07v5-potential-annotation-training-recipe-census',
                  scope='original predictive planning targets; not every executed endpoint',
                  execution_evidence='completed_stages absent from saved audit projection',
                  duplicate_interpretation='potential planned equality, not executed proven hits',
                  mask_only_interpretation='upper bound within original context; not proved reuse',
                  input_bindings=bindings, requests=results, statuses=counts,
                  counts=summarize([row for case in results for row in case.get('recipes', [])]),
                  counts_by_arm={arm: summarize([row for case in results
                                                for row in case.get('recipes', [])
                                                if row['arm'] == arm]) for arm in ARMS},
                  inference_rerun=False, cache_implemented=False,
                  speed_qualification=False, accuracy_qualification=False)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'census.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(output=str(output / 'census.json'), statuses=counts,
                          counts=report['counts'])))
    return int(bool(counts['mismatching'] or counts['missing']))


if __name__ == '__main__':
    raise SystemExit(main())
