"""Bounded automatic ALGO03 recovery over an isolated ALGO02 analysis export.

This adapter produces shadow decisions, never production position contracts.
The frozen numerical implementation is reused in audited child processes.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

from leo.application.automatic_fast_graph import execute

ARMS = ('c0', 'fitted_c')
POLICY = 'algo03-bounded-recovery-v1'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def select_targets(inventory, limit=8):
    """Rank common unused native supports identically in both arms, without GPS."""
    by_arm = {a: {r['track_id']: r for r in inventory['tracks'] if r['arm'] == a}
              for a in ARMS}
    selected = []
    for tid, row in by_arm['c0'].items():
        other = by_arm['fitted_c'].get(tid)
        if other is None:
            continue
        if not all(r['current_large'] for r in (row, other)):
            continue
        ids = set(row['observation_ids'])
        if ids != set(other['observation_ids']) or not ids <= set(row['all_track_observation_ids']):
            continue
        selected.append(dict(row, inactive_fragment=ids != set(row['all_track_observation_ids'])))
    selected.sort(key=lambda r: (-len(r['observation_ids']), r['track_id']))
    return selected[:limit], len(selected)


def scientific_receipts(paths):
    return {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}


def joint_pair(candidates):
    """Choose one disjoint native pair by scored support, never location error."""
    pairs = []
    for i, first in enumerate(candidates):
        for second in candidates[i+1:]:
            pair = [first, second]
            if any(q['kind'] != 'new_family' or q.get('inactive_fragment') for q in pair):
                continue
            if first['targets'][0]['norad'] == second['targets'][0]['norad']:
                continue
            ids = [o for q in pair for t in q['targets'] for o in t['observation_ids']]
            if len(ids) == len(set(ids)):
                pairs.append((len(ids), pair))
    return max(pairs, key=lambda p: p[0])[1] if pairs else []


def scoped_pair(inventory, arms, owners, targets):
    """Credit only original incumbent IDs plus the explicitly scored targets."""
    wanted_targets = {o for t in targets for o in t['observation_ids']}
    if len(wanted_targets) != sum(len(t['observation_ids']) for t in targets):
        raise ValueError('Duplicate target observation')
    pair = {}
    for arm in ARMS:
        old = (set(inventory['publication_support'][arm]['owners']) if 'publication_support' in inventory
               else set(inventory['policy'][arm]['proposed_associated_ids']))
        wanted = old | wanted_targets
        if old & wanted_targets or not wanted <= set(owners[arm]):
            raise ValueError('Lost incumbent or overlapping/unverified target')
        for t in targets:
            if any(owners[arm][o] != t['norad'] for o in t['observation_ids']):
                raise ValueError('Target ownership differs from scored satellite')
        xy = arms[arm]['endpoint_east_north_km']
        if len(xy) != 2 or not all(math.isfinite(v) and abs(v) <= 12.5 for v in xy):
            raise ValueError('Invalid regional endpoint')
        pair[arm] = dict(endpoint_east_north_km=xy,
                         endpoint_latlon=arms[arm]['endpoint_latlon'],
                         negative_twice_elbo=arms[arm]['negative_twice_elbo'],
                         associated_ids=sorted(wanted),
                         owners={o: owners[arm][o] for o in sorted(wanted)},
                         added_points=len(wanted_targets))
    if pair['c0']['owners'] != pair['fitted_c']['owners']:
        raise ValueError('Paired observation identities or satellites differ')
    return pair


def single_candidate(inventory, trial, shared):
    control = read(trial / 'control.json')
    addition = read(trial / ('target_0.json' if shared else 'new_family.json'))
    audit = read(trial / 'exact_owner_replay.json')
    if not (control['paired_valid'] and addition['paired_valid'] and audit['all_verified']):
        return None
    if shared:
        # The frozen shared-family reports validate physical residuals but do
        # not require the position optimizer to finish. Qualify every matched
        # fit here, including the control, before publishing a new endpoint.
        for document in (control, addition):
            for arm in ARMS:
                history = document['arms'][arm].get('history', [])
                if not history:
                    return None
                fit = history[-1].get('fit', {})
                completed = (fit['success'] is True if 'success' in fit else
                             fit.get('stopped') == 'small_step_and_improvement')
                if not completed:
                    return None
    protocol = read(trial / 'protocol.json')
    role = 'target_0' if shared else 'new_family'
    rows = {r['arm']: r for r in audit['rows'] if r['role'] == role}
    # Shared audit records replayed ownership indirectly; its exact replay has
    # already compared these stored owner maps with the rebuilt model.
    owners = {a: addition['arms'][a]['proposed_owners'] if shared else rows[a]['owners']
              for a in ARMS}
    pair = scoped_pair(inventory, addition['arms'], owners, protocol['targets'])
    return dict(kind='shared_family' if shared else 'new_family', arms=pair,
                targets=protocol['targets'], trial=str(trial),
                inactive_fragment=bool(protocol.get('inactive_fragment_sources')),
                source_receipts=scientific_receipts([trial / name for name in (
                    'protocol.json', 'control.json', 'target_0.json' if shared else 'new_family.json',
                    'exact_owner_replay.json')]))


def run(output, maximum_seconds):
    began = time.monotonic()
    descriptor = read(output / 'snapshot/descriptor.json')
    baseline = descriptor['terminal']
    result = dict(policy=POLICY, shadow_only=True, production_changed=False,
                  job_id=descriptor['job_id'], baseline=baseline, decision='ALGO02_fallback',
                  selected=None, attempts=[], stages=[], maximum_seconds=maximum_seconds,
                  no_GPS_selection=True, causal_only=True, matched_c_arms=True,
                  ranking='largest commonly unused native support, then stable track ID; at most eight',
                  limitations=['at most eight targets assessed and two new families jointly included',
                               'partial/shared/same-family combinations remain individual alternatives',
                               'no joint numerical retry without a complete matched factorized diagnostic'])
    qualified = []

    def stage(name, script, *arguments):
        remaining = maximum_seconds - 5 - (time.monotonic() - began)
        receipt = dict(name=name, status='budget_exhausted')
        if remaining > 1:
            command = [sys.executable, '-B', str(Path(__file__).with_name(script)),
                       *map(str, arguments)]
            start = time.monotonic()
            receipt.update(command=command, budget_seconds=min(600, remaining))
            try:
                with (output / (name + '.log')).open('xb') as log:
                    code = execute(command, log=log, timeout=receipt['budget_seconds'])
                receipt.update(status='complete' if code == 0 else 'failed', returncode=code)
            except Exception as error:
                receipt.update(status='failed', error=f'{type(error).__name__}: {error}')
            receipt['seconds'] = time.monotonic() - start
        result['stages'].append(receipt)
        write(output / (name + '-receipt.json'), receipt)
        return receipt['status'] == 'complete'

    try:
        root = Path(descriptor['root'])
        for relative, expected in descriptor['files'].items():
            actual = 'sha256:' + hashlib.sha256((root / relative).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError('Snapshot changed: ' + relative)
        job = dict(root=str(root), case='SCAN', job_id=descriptor['job_id'],
                   identities=[descriptor['session_id']], label='SCAN', aliases=['SCAN'],
                   scopes=['production shadow'], policy_kind='baseline')
        write(output / 'inventory-job.json', job)
        folder = output / 'all-large-track-recovery' / job['job_id']
        inventory_path = folder / 'inventory.json'
        if not stage('inventory', 'algo03_inventory.py', '--job',
                     output / 'inventory-job.json', '--output', folder,
                     '--descriptor', output / 'snapshot/descriptor.json'):
            raise ValueError('Inventory failed')
        inventory = read(inventory_path)
        proof = read(folder / 'publication_support.json')
        if not proof['all_verified']:
            raise ValueError('Baseline ownership replay failed')
        result['source_support'] = proof['arms']
        result['source_support_receipt'] = scientific_receipts([folder / 'publication_support.json'])
        inventory['publication_support'] = proof['arms']
        targets, count = select_targets(inventory)
        result.update(inventory_summary=inventory['summary'], eligible_tracks=count,
                      selected_track_ids=[t['track_id'] for t in targets])
        write(output / 'selected-tracks.json', targets)
        for index, target in enumerate(targets):
            tid = target['track_id']
            annotation = output / tid / 'annotation'
            trial = output / tid / 'trial'
            attempt = dict(track_id=tid, points=len(target['observation_ids']), status='not_started')
            result['attempts'].append(attempt)
            # Keep enough wall time for a final joint fit. All omissions remain
            # in the decision, including targets after the discovery budget.
            discovery_budget = min(600., maximum_seconds * .7)
            if time.monotonic() - began > discovery_budget:
                attempt['status'] = 'discovery_budget_exhausted'
                continue
            fragment_options = ['--inactive-fragment'] if target['inactive_fragment'] else []
            if not stage(f'target-{index}-annotation', 'annotate_predictive_only.py',
                         '--inventory', inventory_path, '--track', tid, '--output', annotation,
                         '--predictive-member', '--uncalibrated-phase-mixture',
                         '--distinct-partitions', '--shifted-block-origin', '--candidates', 12,
                         *fragment_options):
                attempt['status'] = 'annotation_execution_failed'
                continue
            from annotation_partition_plan import require_distinct_annotation
            from leo.analysis.research.grouped_prediction import identity_consensus
            from test_predictive_graph_transfer import shared_family_route
            r = read(annotation / 'result.json')
            vote = identity_consensus(r['folds'], score_name='conditional_target')
            attempt['annotation'] = vote
            if vote['status'] != 'conditionally_supported_identity':
                attempt['status'] = vote['status']
                continue
            require_distinct_annotation(r, read(annotation / 'protocol.json'))
            shared = shared_family_route(r['folds'], vote['norad'])
            attempt['shared_family'] = shared
            options = ['--predictive-member'] if shared else ['--uncalibrated-label', '--phase-step', '.025']
            if not stage(f'target-{index}-inclusion',
                         'include_predictive_annotations.py' if shared else 'include_new_predictive_family.py',
                         '--inventory', inventory_path, '--validation', annotation, '--output', trial, *options):
                attempt['status'] = 'inclusion_execution_failed'
                continue
            if not stage(f'target-{index}-audit',
                         'audit_shared_predictive_inclusion.py' if shared else 'audit_predictive_family_inclusion.py',
                         '--study', output, '--trial', trial, '--output', trial / 'exact_owner_replay.json'):
                attempt['status'] = 'audit_execution_failed'
                continue
            candidate = single_candidate(inventory, trial, shared)
            if not shared and candidate is None:
                from retry_predictive_numerical_failures import numerical_only
                if numerical_only(read(trial / 'control.json'), read(trial / 'new_family.json'),
                                  read(trial / 'exact_owner_replay.json')):
                    retry = output / tid / 'numerical-retry'
                    attempt['numerical_retry'] = dict(original_trial=str(trial), retry_trial=str(retry))
                    ok = stage(f'target-{index}-retry', 'include_new_predictive_family.py',
                               '--inventory', inventory_path, '--validation', annotation,
                               '--output', retry, '--uncalibrated-label', '--phase-step', '.025', '--optimizer', 'powell')
                    if ok:
                        ok = stage(f'target-{index}-retry-audit', 'audit_predictive_family_inclusion.py',
                                   '--study', output, '--trial', retry, '--output', retry / 'exact_owner_replay.json')
                    if ok:
                        candidate = single_candidate(inventory, retry, False)
            attempt['status'] = 'RF_qualified' if candidate else 'RF_rejected'
            if candidate:
                qualified.append(candidate)
        # A deterministic fallback uses the first RF-qualified target in the
        # predeclared ranking. Separate individual fits are never added together.
        if qualified:
            result.update(selected=qualified[0], decision='ALGO03_single')
        pair = joint_pair(qualified)
        if pair:
            probe = output / 'joint-probe'
            ok = stage('joint-probe', 'probe_joint_predictive_families.py', '--study', output,
                       '--trials', *(q['trial'] for q in pair), '--output', probe, '--phase-step', '.0625')
            completed = ok
            for method in ('control', 'factorized', 'joint'):
                for arm in ARMS:
                    if not completed:
                        break
                    trial = output / 'joint' / (method + '-' + arm)
                    ok = stage(method + '-' + arm, 'fit_two_predictive_families.py', '--study', output,
                               '--probe', probe, '--output', trial, '--method', method, '--arm', arm)
                    if ok:
                        ok = stage(method + '-' + arm + '-audit', 'audit_two_predictive_families.py',
                                   '--study', output, '--trial', trial, '--output', trial / 'audit.json')
                    completed = ok
                    if ok and method == 'joint':
                        # Preserve the frozen numerical retry entrypoint's
                        # historical audit filename without changing its bytes.
                        write(trial / 'audit-v2.json', read(trial / 'audit.json'))
            joint_root = output / 'joint'
            passed = completed and all(read(joint_root / (m + '-' + a) / 'audit.json')['RF_qualified_arm']
                                       for m in ('control', 'joint') for a in ARMS)
            if completed and not passed:
                audits = [read(joint_root / (m + '-' + a) / 'audit.json')
                          for m in ('control', 'factorized', 'joint') for a in ARMS]
                fits = [read(joint_root / (m + '-' + a) / 'result.json')
                        for m in ('control', 'factorized', 'joint') for a in ARMS]
                numerical = (any(not r['history'][-1]['success'] for r in fits)
                             and all(not r['incumbent_owner_changes'] and r['phase_check']['phase_change_s'] <= .01
                                     and all(v['all_pass'] for v in r['exact_incumbent_orbits'])
                                     and all(v for k, v in r['checks'].items() if k != 'incumbent_and_numerical')
                                     for r in audits))
                if numerical:
                    retry_root = output / 'joint-retry'
                    ok = True
                    for method in ('control', 'factorized', 'joint'):
                        for arm in ARMS:
                            if not ok:
                                break
                            trial = retry_root / (method + '-' + arm)
                            ok = stage('retry-' + method + '-' + arm, 'retry_two_family_positions.py',
                                       '--study', output, '--source', joint_root, '--output', trial,
                                       '--method', method, '--arm', arm)
                            if ok:
                                ok = stage('retry-' + method + '-' + arm + '-audit', 'audit_two_predictive_families.py',
                                           '--study', output, '--trial', trial, '--output', trial / 'audit.json')
                    passed = ok and all(read(retry_root / (m + '-' + a) / 'audit.json')['RF_qualified_arm']
                                        for m in ('control', 'joint') for a in ARMS)
                    if passed:
                        joint_root = retry_root
            if passed:
                arms = {a: read(joint_root / ('joint-' + a) / 'result.json') for a in ARMS}
                owners = {a: read(joint_root / ('joint-' + a) / 'audit.json')['owners'] for a in ARMS}
                entries = [t for q in pair for t in q['targets']]
                candidate = dict(kind='joint', targets=entries, arms=scoped_pair(inventory, arms, owners, entries),
                    source_receipts=scientific_receipts([p for m in ('control', 'joint') for a in ARMS
                        for p in (joint_root / (m + '-' + a) / 'result.json', joint_root / (m + '-' + a) / 'audit.json')]))
                if candidate['arms']['c0']['added_points'] > result['selected']['arms']['c0']['added_points']:
                    result.update(decision='ALGO03_joint', selected=candidate)
        if result['selected']:
            for arm in ARMS:
                if any(result['selected']['arms'][arm]['owners'].get(o) != n
                       for o, n in result['source_support'][arm]['owners'].items()):
                    raise ValueError('Selected candidate changed an incumbent owner')
            from leo.contracts.fast_graph_position_v2 import RF_CHECKS
            result['rf_checks'] = {key: True for key in RF_CHECKS}
    except Exception as error:
        result.update(decision='ALGO02_fallback', selected=None,
                      failure=f'{type(error).__name__}: {error}')
    result['seconds'] = time.monotonic() - began
    write(output / 'decision.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--maximum-seconds', type=int, choices=range(1, 1201), default=1200)
    args = parser.parse_args()
    def terminate(signum, frame):
        raise RuntimeError('Shadow supervisor deadline')
    signal.signal(signal.SIGTERM, terminate)
    run(args.output.resolve(), args.maximum_seconds)
