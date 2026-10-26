"""Archived own-source nomination availability, before new target diagnostics."""
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
PRIOR = Path('/srv/bulk/leo/research/ds24-ambiguity-policy-r01/qualification')
OWNERS = Path('/srv/bulk/leo/research/ds24-ambiguity-position-r01/inventory/ownership/DS24-0015/parent.json')
CASE = 'DS24-0015'
NORAD = 68904
D = 'DS24-0015-RX2-CH4-T004-RF11690312500.000000'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def own_label(row):
    value = row.get('candidate_norad', row.get('norad'))
    return None if value is None else int(value)


def classify(row, target_ids, accepted):
    ids = row['observation_ids']
    evidence = row['archived_own_label_evidence']
    relevant = [q for q in evidence if q['norad'] == NORAD]
    overlap = {arm: sorted(set(ids) & set(values)) for arm, values in accepted.items()}
    reasons = []
    if row['component'] == D:
        reasons.append('discovery_owner')
    if set(ids) & set(target_ids):
        reasons.append('discovery_native_ID_overlap')
    if any(overlap.values()):
        reasons.append('original_accepted_ID_overlap')
    if not relevant:
        reasons.append('no_persisted_own_68904_nomination_in_audited_fields')
    return dict(row, relevant_68904_evidence=relevant, accepted_overlap=overlap,
        eligible_potential_separate_owner=not reasons, exclusion_reasons=reasons,
        complete_alternative_feasibility_list_available=False,
        missing_feasibility_list_is_not_negative_evidence=True,
        identity_independently_validated=False)


def build():
    began = time.monotonic()
    base = SOURCE / CASE
    paths = [base / name for name in ('tracks.json', 'observations.json', 'fit_radio_noise.json',
              'result.json', 'algo02_result.json', 'nominal_elements.json', 'radio_noise.json', 'receipt.json')]
    canonical_path = SOURCE / 'family_cavity/position' / (CASE + '.json')
    paths += [canonical_path, OWNERS, PRIOR / 'protocol.json', PRIOR / 'RF_seal.json', Path(__file__)]
    tracks = read(base / 'tracks.json')
    observations = {q['observation_id']: q for q in read(base / 'observations.json')}
    fit, result, algo = [read(base / name) for name in ('fit_radio_noise.json', 'result.json', 'algo02_result.json')]
    canonical = read(canonical_path)
    node = canonical['selected']['node'] if canonical['accepted'] else canonical['baseline_node']
    evidence = {track['key']: [] for track in tracks}

    def add(row, provenance, shared_calibration):
        component = row.get('component')
        label = own_label(row)
        if component not in evidence or label is None:
            return
        evidence[component].append(dict(norad=label, candidate_index=row.get('candidate_index'),
            compatible=row.get('compatible'), feasible_candidates=row.get('feasible_candidates'),
            provenance=provenance, original_joint_calibration_may_include_D=shared_calibration,
            not_new_independent_identity_validation=True))

    for row in node['seed']['rows']:
        add(row, 'canonical_family_cavity_node_seed', True)
    for choice in fit['choices']:
        for row in choice['node']['seed']['rows']:
            add(row, 'original_radio_hypothesis_' + str(choice['hypothesis']), True)
    for row in result['final_node']['seed']['rows']:
        add(row, 'initial_algorithm_final_node', True)
    for trim in result['trims']:
        for number, row in enumerate(trim.get('alternatives', [])):
            add(dict(row, component=trim['component']), 'original_salvage_alternative_' + str(number), True)
        if trim.get('selected'):
            add(dict(trim['selected'], component=trim['component']), 'original_salvage_selected', True)
    for row in algo['linear_entries']:
        add(row, 'ALGO02_predictive_offer', True)
    parent = read(OWNERS)
    accepted = {arm: parent['coverage'][arm]['accepted_observation_ids'] for arm in ('c0', 'fitted_c')}
    target = next(track for track in tracks if track['key'] == D)
    rows = []
    for track in tracks:
        ids = list(track['observation_ids'])
        if len(set(ids)) != len(ids) or any(oid not in observations for oid in ids):
            raise ValueError('Nonunique/missing native owner ID')
        rows.append(classify(dict(component=track['key'], receiver=track['receiver'],
            channel=track['channel'], rf_hz=track['rf_hz'], bank=track['bank'],
            source_id=track['source_id'], points=len(ids), start_s=track['start_s'], end_s=track['end_s'],
            quality_status=track['quality_status'], observation_ids=ids,
            archived_own_label_evidence=evidence[track['key']]), target['observation_ids'], accepted))
    eligible = [q for q in rows if q['eligible_potential_separate_owner']]
    summary = dict(case=CASE, fixed_hypothesis=NORAD, discovery_component=D,
        complete_original_owners=len(rows), original_GLRT_native_observations=len(observations),
        owners_with_persisted_68904_evidence=sum(bool(q['relevant_68904_evidence']) for q in rows),
        potential_separate_owner_count=len(eligible),
        potential_separate_owners=[q['component'] for q in eligible],
        all_complete_owner_rows=rows,
        no_new_catalogue_nomination_or_CFO_comparison=True,
        selection_rule='All complete other owners with their own archived68904 label, no D/native/accepted overlap; all receivers, bands and original source classes',
        absence_scope='No own68904 nomination in the listed persisted seed/hypothesis/salvage/predictive fields does not establish physical absence; full alternative feasible-candidate lists are not persisted here',
        graph_and_original_joint_calibration_selection_exposed=True,
        no_source_forced_to_68904=True,
        bindings={str(path): sha(path) for path in paths},
        seconds=time.monotonic() - began)
    with (HERE / 'inventory.json').open('x') as stream:
        json.dump(summary, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: summary[key] for key in ('complete_original_owners', 'owners_with_persisted_68904_evidence', 'potential_separate_owner_count', 'potential_separate_owners', 'seconds')}))


if __name__ == '__main__':
    build()
