"""Chronological archived-source transfer; baseline remains operational."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
R2 = Path('/srv/bulk/leo/research/ds24-uncertain-new-family-r01')
RECOVERY = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path.insert(0, str(RECOVERY))
sys.path.insert(0, str(R2/'scientific'))
import adapter as original
import quadrature02 as q
import execution03 as controls
import recovery as r

ARMS = ('c0', 'fitted_c')
BRANCHES = original.BRANCHES
NODES = 1281
ARM_SECONDS = 180.
GLOBAL_SECONDS = 1200.


def write(path, value):
    r.write_new(path, value)


def timeout(seconds, message):
    if seconds <= 0:
        raise TimeoutError(message)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError(message)))
    signal.setitimer(signal.ITIMER_REAL, seconds)


def prepare_ownership():
    """Unchanged saved parent positions/references; no position fit/nomination."""
    began = time.monotonic()
    inventory_path = R2/'next_inventory/inventory.json'
    inventory = r.read(inventory_path)
    candidates = inventory['provisional_rejected_graph_bindings']
    expected = sorted(candidates, key=lambda x:(x['recording_utc_ns'], x['case'], x['source_id'], x['component']))
    if candidates != expected or len(candidates) != 97:
        raise ValueError('original inventory/order changed')
    if (HERE/'panel.json').exists():
        raise FileExistsError('freeze a new revision rather than rerun ownership')
    panel, exclusions, ledgers = [], [], []
    cases = list(dict.fromkeys(row['case'] for row in candidates))
    for case in cases:
        if len(panel) == 4:
            break
        if case in ('DS24-0095', 'DS24-0087'):
            raise ValueError('development cases excluded')
        start = time.monotonic()
        timeout(min(60., 300.-(start-began)), 'ownership reconstruction cap')
        try:
            d = r.context(case)
            coverage = {arm:r.membership(d, arm, d['arms'][arm]) for arm in ARMS}
            valid = all(controls.original_single_arm_valid(
                r.summary(r.build(d, arm, d['arms'][arm]['phase_reference']),
                          np.asarray(d['arms'][arm]['endpoint_east_north_km']), d['entries']),
                d['arms'][arm]['final_phase_change_s']) for arm in ARMS)
            if not valid:
                raise ValueError('unchanged saved parent fails original validity')
            parent = dict(case=case, status='complete', original_positions_and_references=d['arms'],
                coverage=coverage, original_protected=sorted(d['original_protected']),
                source_parent_sha256=r.sha(r.SOURCE/'family_cavity/position'/(case+'.json')),
                source_tracks_sha256=r.sha(r.SOURCE/case/'tracks.json'),
                source_observations_sha256=r.sha(r.SOURCE/case/'observations.json'),
                seconds=time.monotonic()-start, position_fits=0, nominations=0, GPS_used=False)
            write(HERE/'ownership'/case/'parent.json', parent)
            ledgers.append(dict(case=case, status='complete', parent_path=str(HERE/'ownership'/case/'parent.json'),
                                seconds=parent['seconds']))
            for row in (row for row in candidates if row['case'] == case):
                ids = set(row['observation_ids'])
                overlap = {arm:sorted(ids & set(coverage[arm]['accepted_observation_ids'])) for arm in ARMS}
                reasons = []
                k = row['parent_row_index']; sl = d['base'].slices[k]
                i = d['base'].members[k]; track = d['scan'].tracks[i]
                if any(overlap.values()): reasons.append('parent accepted-ID overlap including postfit-only extensions')
                if d['keep'][sl].any(): reasons.append('already curved calibration')
                if row['candidate_index'] in d['original_protected']: reasons.append('family active in parent likelihood')
                if i not in d['scan'].curved: reasons.append('not original active curvature')
                if track['key'] != row['component'] or track['observation_ids'] != row['observation_ids']:
                    reasons.append('original native source/order mismatch')
                if d['node']['aliases'][k] != row['alias'] or d['base'].rows[k]['candidate_index'] != row['candidate_index']:
                    reasons.append('archived nominee/alias mismatch')
                if reasons:
                    exclusions.append(dict(case=case, component=row['component'], reasons=reasons,
                                           accepted_ID_overlap=overlap))
                    continue
                chosen = copy.deepcopy(row)
                chosen.update(full_accepted_ID_ledger_present=True,
                    full_accepted_ID_overlap_verified_both_arms=True,
                    fully_bound_raw_transfer_candidate=True,
                    accepted_ID_overlap={arm:[] for arm in ARMS},
                    parent_ledger_sha256=r.sha(HERE/'ownership'/case/'parent.json'),
                    parent_ledger_path=str(HERE/'ownership'/case/'parent.json'),
                    status='archived rejected nominee, predictive experiment only',
                    qualified_association=False)
                panel.append(chosen)
                break
        except Exception as exc:
            failure = dict(case=case, status='failed', error=repr(exc), traceback=traceback.format_exc(),
                           seconds=time.monotonic()-start, position_fits=0, nominations=0)
            write(HERE/'ownership'/case/'failure.json', failure)
            ledgers.append(failure)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    record = dict(panel=panel, selected_count=len(panel), maximum=4,
        ordering='original inventory: recording UTC, scan ID, original source_id, component; one source per distinct scan',
        original_inventory_sha256=r.sha(inventory_path), ledgers=ledgers, exclusions=exclusions,
        stopped_after_first_four_eligible_scans=len(panel)==4,
        position_fits=0, nominations=0, GPS_used=False,
        seconds=time.monotonic()-began, source_sha256=r.sha(Path(__file__)))
    write(HERE/'panel.json', record)
    print(json.dumps(dict(selected_count=len(panel), seconds=record['seconds'],
        panel=[{key:row[key] for key in ('case', 'component', 'candidate_norad', 'alias', 'points')} for row in panel]), indent=2), flush=True)


def load_target(row):
    d = r.context(row['case'])
    parent_path = Path(row['parent_ledger_path'])
    if r.sha(parent_path) != row['parent_ledger_sha256']:
        raise ValueError('full parent accepted-ID ledger changed')
    d['parent_membership'] = r.read(parent_path)['coverage']
    i = next(i for i, t in enumerate(d['scan'].tracks) if t['key'] == row['component'])
    track = d['scan'].tracks[i]; j = row['candidate_index']
    if track['observation_ids'] != row['observation_ids']:
        raise ValueError('target native ID order changed')
    if any(set(row['observation_ids']) & set(d['parent_membership'][arm]['accepted_observation_ids']) for arm in ARMS):
        raise ValueError('target overlaps complete parent accepted IDs')
    bank, metadata = original.build_modes(d['scan'], [j], [j], 'physical')
    target = dict(row, track_index=i, row_index=row['parent_row_index'],
        norad=row['candidate_norad'], phase_mean_s=float(d['all_means'][j]),
        phase_sd_s=float(d['widths'][j]), phase_nu=d['model']['nu'],
        target_local_shape_metadata=metadata, rf_hz=track['rf_hz'])
    entry = dict(component=row['component'], candidate_index=j, norad=row['candidate_norad'],
        track_index=i, alias=row['alias'], observation_ids=row['observation_ids'], points=row['points'])
    sky = dict(time_s=d['scan'].sky['time_s'],
        position_km=d['scan'].sky['position_km'][[j]], velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    d.update(target=target, target_entry=entry, target_track=track,
             target_sky=sky, target_mode_bank=bank)
    return d


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('ownership',), required=True)
    args = parser.parse_args()
    prepare_ownership()
