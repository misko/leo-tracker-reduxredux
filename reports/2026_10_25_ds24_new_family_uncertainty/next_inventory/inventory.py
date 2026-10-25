"""Metadata-only archived DS24 proposal feasibility; no numerical inference."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
RUN = Path('/srv/bulk/leo/research/ds25-20261024')
MOVEMENT = Path('/srv/bulk/leo/research/ds24-movement-policy-r01')
EXCLUDE = {'DS24-0095', 'DS24-0087'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, data):
    with Path(path).open('x') as stream:
        if isinstance(data, str):
            stream.write(data)
        else:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write('\n')


def run():
    began = time.monotonic(); bindings = {}
    def read(path):
        bindings[str(path)] = sha(path)
        return json.loads(Path(path).read_text())
    ledger_path = MOVEMENT/'cohort_ledger.json'
    ledger = read(ledger_path)
    rows_by_case = {row['case']:row for row in ledger['rows']}
    cases = sorted((case for case in ledger['eligible_cases'] if case not in EXCLUDE),
                   key=lambda case:(rows_by_case[case]['captured_utc_ns'], case))
    provisional, case_rows, screened = [], [], []
    rejection_counts = Counter()
    for case in cases:
        parent_path = RUN/'family_cavity/position'/(case+'.json')
        parent = read(parent_path)
        tracks_path = RUN/case/'tracks.json'; tracks = read(tracks_path)
        observations_path = RUN/case/'observations.json'; observations = read(observations_path)
        by_key = {track['key']:track for track in tracks}
        native = {row['observation_id'] for row in observations}
        selected = parent['selected'] if parent['accepted'] else None
        node = selected['node'] if selected else parent['baseline_node']
        entries = selected['entries'] if selected else parent['baseline_entries']
        seed_rows = [row for row in node['seed']['rows'] if row['active_curvature']]
        if len(seed_rows) != len(node['aliases']):
            raise ValueError('archived curved row/alias order is not explicit')
        offset, slices = 0, []
        for row in seed_rows:
            n = len(by_key[row['component']]['observation_ids'])
            slices.append(parent['original_mask'][offset:offset+n]); offset += n
        if offset != len(parent['original_mask']):
            raise ValueError('archived full mask cannot be bound statically')
        active = {row['candidate_index'] for row, keep in zip(seed_rows, slices) if any(keep)}
        active |= {entry['candidate_index'] for entry in entries}
        parent_likelihood = {oid for row, keep in zip(seed_rows, slices)
                             for oid, retain in zip(by_key[row['component']]['observation_ids'], keep) if retain}
        parent_likelihood |= {oid for entry in entries for oid in entry['observation_ids']}
        known_accepted = {arm:{oid for row in parent['policy_arms'][arm]['gates']['tracks']+
            parent['policy_arms'][arm].get('linear_gates', []) if row['compatible']
            for oid in row['observation_ids']} for arm in ('c0', 'fitted_c')}
        specialized_parent = MOVEMENT/'recovery'/case/'parent.json'
        complete_accepted = None
        if specialized_parent.exists():
            saved_parent = read(specialized_parent)
            complete_accepted = {arm:set(saved_parent['coverage'][arm]['accepted_observation_ids'])
                                 for arm in ('c0', 'fitted_c')}
        specialized_nomination = MOVEMENT/'recovery'/case/'graph/nominations.json'
        if specialized_nomination.exists():
            screened.append(dict(case=case, path=str(specialized_nomination), sha256=sha(specialized_nomination)))
        cavity_path = RUN/'family_cavity'/(case+'_nominations.json')
        cavity = read(cavity_path)
        meta = rows_by_case[case]
        utc = datetime.fromtimestamp(meta['captured_utc_ns']/1e9, timezone.utc).isoformat()
        count = 0
        for index, (row, keep, alias) in enumerate(zip(seed_rows, slices, node['aliases'])):
            track = by_key[row['component']]; ids = track['observation_ids']
            if any(keep):
                rejection_counts['active_parent_curve'] += 1; continue
            if row['candidate_index'] in active:
                rejection_counts['family_already_in_parent_likelihood'] += 1; continue
            if len(ids) != len(set(ids)) or len(ids) != len(track['times']) or not set(ids) <= native:
                rejection_counts['native_ID_binding_incomplete'] += 1; continue
            if set(ids) & parent_likelihood:
                rejection_counts['parent_likelihood_ID_overlap'] += 1; continue
            if any(set(ids)&accepted for accepted in known_accepted.values()):
                rejection_counts['known_accepted_ID_overlap'] += 1; continue
            if complete_accepted is not None and any(set(ids)&accepted for accepted in complete_accepted.values()):
                rejection_counts['complete_accepted_ID_overlap'] += 1; continue
            fully_bound = complete_accepted is not None
            provisional.append(dict(case=case, recording_utc=utc,
                recording_utc_ns=meta['captured_utc_ns'], recording_id=meta['recording_id'],
                source_id=track['source_id'], component=track['key'], parent_row_index=index,
                candidate_index=row['candidate_index'], candidate_norad=row['candidate_norad'],
                alias=alias, receiver=track['receiver'], channel=track['channel'],
                RF_hz=track['rf_hz'], points=len(ids), observation_ids=ids,
                active_curvature_persisted=row['active_curvature'],
                active_curvature_provenance='archived original full graph seed flag; FixedFamilies asserts member set equals scan.curved; no rule recomputation',
                whole_source=True, offered_new_family_RX_channel_owners=1,
                parent_family_inactive=True, parent_likelihood_ID_overlap=0,
                original_nomination_compatible=row['compatible'],
                parent_final_mask_rejected_whole_source=True,
                known_curved_predictive_accepted_overlap={arm:len(set(ids)&accepted) for arm,accepted in known_accepted.items()},
                full_accepted_ID_ledger_present=complete_accepted is not None,
                full_accepted_ID_overlap_verified_both_arms=complete_accepted is not None,
                fully_bound_raw_transfer_candidate=fully_bound,
                screened_single_curved_recovery_proposal=False,
                qualified_association=False,
                missing_prerequisite=None if fully_bound else 'no archived both-arm complete accepted-ID ledger including postfit-only extensions',
                parent_path=str(parent_path), tracks_path=str(tracks_path), observations_path=str(observations_path)))
            count += 1
        case_rows.append(dict(case=case, recording_utc=utc, recording_utc_ns=meta['captured_utc_ns'],
            archived_curved_nomination_rows=len(seed_rows),
            cavity_replacement_family_units=len(cavity.get('families', [])),
            provisional_rejected_graph_bindings=count,
            complete_accepted_ID_ledger_present=complete_accepted is not None,
            specialized_recovery_nomination_present=specialized_nomination.exists()))
    provisional.sort(key=lambda row:(row['recording_utc_ns'], row['case'], row['source_id'], row['component']))
    ready = [row for row in provisional if row['fully_bound_raw_transfer_candidate']]
    for name in ('evaluate_ds23_phase_refreshed.py', 'prototype_dsx01_continuous_position.py',
                 'localize_merged_track_catalogue.py'):
        path = Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools')/name
        bindings[str(path)] = sha(path)
    result = dict(scope='existing archived metadata only', excluded_cases=sorted(EXCLUDE),
        fast_population_count=len(ledger['eligible_cases']), inspected_additional_cases=len(cases),
        ordering='recording UTC ascending, scan ID, source ID, component',
        specialized_screened_recovery_proposals=screened,
        specialized_screened_recovery_proposal_count=len(screened),
        fully_bound_raw_transfer_candidate_count=len(ready),
        first_four_fully_bound_raw_candidates=ready[:4],
        provisional_rejected_graph_binding_count=len(provisional),
        provisional_rejected_graph_bindings=provisional, cases=case_rows,
        static_exclusion_counts=dict(rejection_counts),
        no_GPS_or_error_lookup=True, no_context_loader=True, no_propagation=True,
        no_nomination=True, no_fit=True, no_new_RF_gates=True, no_selector_tuning=True,
        no_active_curvature_recomputation=True,
        accepted_ID_requirement='must include postfit-only accepted IDs in both arms; curved/predictive gates alone are insufficient',
        source_sha256=sha(Path(__file__)), input_sha256=bindings,
        elapsed_seconds=time.monotonic()-began)
    write_new(HERE/'inventory.json', result)
    text = f'''# Archived DS24 transfer feasibility inventory

**Zero additional fully bound raw transfer candidates and zero specialized
single-curved recovery proposal ledgers were established outside 0095/0087.**
This metadata-only inventory inspected all {len(cases)} remaining cases in the
frozen 24-scan DS24 fast cohort. It did not propagate, nominate, fit, evaluate RF
gates, inspect geographic errors, or tune a selector.

The archives contain {len(provisional)} rejected full-graph source bindings with
persisted original active-curvature flags, existing candidate/alias/native IDs,
an inactive parent-likelihood family, and no overlap with the stored parent
curved/predictive accepted IDs. They remain **provisional archived graph rows**.
The full both-arm accepted-ID ledger, including postfit-only compatible
extensions, is not archived for these additional cases in the inspected
authorities. Consequently the required complete accepted-ID nonoverlap check
cannot be certified without additional work. No first four candidates are
promoted or invented.

Existing family-cavity nominations are replacement hypotheses for evidence of
already represented families. They are a separate archive class and are not
unused-source one-owner recovery screen receipts. The provisional graph rows
also are not covariance-screened recovery proposals or qualified associations.

`inventory.json` stores every metadata binding and exclusion count, ordered by
recording UTC, scan ID, source ID and component. Active-curvature eligibility
comes from the original persisted full-graph seed flag; no new polynomial fit
or context loader was used. Parent masks, likelihood ownership and available
gate ledgers were inspected statically. Source and input hashes are included.

Feasibility does not authorize a transfer run. A future protocol must first
establish the missing complete accepted-ID ownership ledger, then define its
bounded RF qualification and matched c=0/fitted-c comparison. It must not call
these known rejected/provisional rows validated associations.
'''
    write_new(HERE/'INVENTORY.md', text)
    write_new(HERE/'seal.json', dict(inventory_sha256=sha(HERE/'inventory.json'),
        report_sha256=sha(HERE/'INVENTORY.md'), source_sha256=sha(Path(__file__)),
        no_new_scientific_propagation_or_fit=True))
    print(json.dumps({key:result[key] for key in ('inspected_additional_cases',
        'specialized_screened_recovery_proposal_count', 'fully_bound_raw_transfer_candidate_count',
        'provisional_rejected_graph_binding_count', 'elapsed_seconds')}, indent=2))


if __name__ == '__main__':
    run()
