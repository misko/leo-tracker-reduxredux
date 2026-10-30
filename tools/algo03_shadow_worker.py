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
POLICY = 'algo03-shadow-top2-v1'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def select_targets(inventory):
    """Rank wholly unused native curves identically in both c arms, without GPS."""
    by_arm = {a: {r['track_id']: r for r in inventory['tracks'] if r['arm'] == a}
              for a in ARMS}
    selected = []
    for tid, row in by_arm['c0'].items():
        other = by_arm['fitted_c'].get(tid)
        if other is None:
            continue
        if not all(r['current_large'] and r['current']['wholly_unassociated']
                   for r in (row, other)):
            continue
        ids = set(row['observation_ids'])
        if ids != set(other['observation_ids']) or ids != set(row['all_track_observation_ids']):
            continue
        selected.append(row)
    selected.sort(key=lambda r: (-len(r['observation_ids']), r['track_id']))
    return selected[:2], len(selected)


def scoped_pair(inventory, arms, owners, targets):
    """Credit only original incumbent IDs plus the explicitly scored targets."""
    wanted_targets = {o for t in targets for o in t['observation_ids']}
    if len(wanted_targets) != sum(len(t['observation_ids']) for t in targets):
        raise ValueError('Duplicate target observation')
    pair = {}
    for arm in ARMS:
        old = set(inventory['policy'][arm]['proposed_associated_ids'])
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
    protocol = read(trial / 'protocol.json')
    role = 'target_0' if shared else 'new_family'
    rows = {r['arm']: r for r in audit['rows'] if r['role'] == role}
    # Shared audit records replayed ownership indirectly; its exact replay has
    # already compared these stored owner maps with the rebuilt model.
    owners = {a: addition['arms'][a]['proposed_owners'] if shared else rows[a]['owners']
              for a in ARMS}
    pair = scoped_pair(inventory, addition['arms'], owners, protocol['targets'])
    return dict(kind='shared_family' if shared else 'new_family', arms=pair,
                targets=protocol['targets'], trial=str(trial))


def run(output, maximum_seconds):
    began = time.monotonic()
    descriptor = read(output / 'snapshot/descriptor.json')
    baseline = descriptor['terminal']
    result = dict(policy=POLICY, shadow_only=True, production_changed=False,
                  job_id=descriptor['job_id'], baseline=baseline, decision='ALGO02_fallback',
                  selected=None, attempts=[], stages=[], maximum_seconds=maximum_seconds,
                  no_GPS_selection=True, causal_only=True, matched_c_arms=True,
                  ranking='largest wholly unassociated native curve, then stable track ID; top two',
                  limitations=['partial tracks deferred', 'at most two targets',
                               'no numerical retry in this bounded adapter',
                               'same-family and mixed-route pairs remain individual alternatives'])
    qualified = []

    def stage(name, script, *arguments):
        remaining = maximum_seconds - (time.monotonic() - began)
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
        if not stage('inventory', 'inventory_all_large_tracks.py', 'one', '--job',
                     output / 'inventory-job.json', '--output', folder):
            raise ValueError('Inventory failed')
        inventory = read(inventory_path)
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
            if not stage(f'target-{index}-annotation', 'annotate_predictive_only.py',
                         '--inventory', inventory_path, '--track', tid, '--output', annotation,
                         '--predictive-member', '--uncalibrated-phase-mixture',
                         '--distinct-partitions', '--shifted-block-origin', '--candidates', 12):
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
            attempt['status'] = 'RF_qualified' if candidate else 'RF_rejected'
            if candidate:
                qualified.append(candidate)
        # A deterministic fallback uses the first RF-qualified target in the
        # predeclared ranking. Separate individual fits are never added together.
        if qualified:
            result.update(selected=qualified[0], decision='ALGO03_single')
        if (len(qualified) == 2 and all(q['kind'] == 'new_family' for q in qualified)
                and qualified[0]['targets'][0]['norad'] != qualified[1]['targets'][0]['norad']):
            probe = output / 'joint-probe'
            ok = stage('joint-probe', 'probe_joint_predictive_families.py', '--study', output,
                       '--trials', *(q['trial'] for q in qualified), '--output', probe, '--phase-step', '.0625')
            for method in ('control', 'joint'):
                for arm in ARMS:
                    if not ok:
                        break
                    trial = output / 'joint' / (method + '-' + arm)
                    ok = stage(method + '-' + arm, 'fit_two_predictive_families.py', '--study', output,
                               '--probe', probe, '--output', trial, '--method', method, '--arm', arm)
                    if ok:
                        ok = stage(method + '-' + arm + '-audit', 'audit_two_predictive_families.py',
                                   '--study', output, '--trial', trial, '--output', trial / 'audit.json')
                    if ok:
                        ok = read(trial / 'audit.json')['RF_qualified_arm']
            if ok:
                arms = {a: read(output / 'joint' / ('joint-' + a) / 'result.json') for a in ARMS}
                owners = {a: read(output / 'joint' / ('joint-' + a) / 'audit.json')['owners'] for a in ARMS}
                entries = [t for q in qualified for t in q['targets']]
                result.update(decision='ALGO03_joint', selected=dict(kind='joint', targets=entries,
                              arms=scoped_pair(inventory, arms, owners, entries)))
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
