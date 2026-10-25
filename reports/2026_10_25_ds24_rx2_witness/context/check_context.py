"""Whitelisted metadata/provenance checks; no new CFO comparisons or inference."""
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent.parent
OLD = RESEARCH / 'ds24-identity-support-r01' / 'witness'
ARMS = ('c0', 'fitted_c')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def owner_metadata(track):
    return {key: track[key] for key in
            ('key', 'receiver', 'channel', 'rf_hz', 'times', 'observation_ids')}


def native_matches(owner, observations):
    return all(
        (observations[oid]['receiver'], observations[oid]['channel'],
         observations[oid]['actual_rf_hz'], observations[oid]['time_s']) ==
        (owner['receiver'], owner['channel'], owner['rf_hz'], stamp)
        for oid, stamp in zip(owner['observation_ids'], owner['times'], strict=True))


def main():
    began = time.monotonic()
    protocol = read(OLD / 'protocol02.json')
    paths = {name: Path(value['path']) for name, value in protocol['input_bindings'].items()}
    bindings = {str(OLD / name): sha(OLD / name) for name in
                ('protocol02.json', 'whole_scan_protocol.json', 'whole_scan_inventory.json',
                 'whole_scan_seal.json', 'geometry_protocol.json', 'geometry_seal.json')}
    for name, path in paths.items():
        assert sha(path) == protocol['input_bindings'][name]['sha256']
        bindings[str(path)] = sha(path)
    source = paths['tracks'].parent
    ownership = read(paths['ownership'])
    assert ownership['source_parent_sha256'] == sha(paths['parent'])
    assert ownership['source_tracks_sha256'] == sha(paths['tracks'])
    observations_path = source / 'observations.json'
    assert ownership['source_observations_sha256'] == sha(observations_path)
    bindings[str(observations_path)] = sha(observations_path)
    observations_list = read(observations_path)
    observations = {row['observation_id']: row for row in observations_list}
    assert len(observations) == len(observations_list) == 4808
    tracks = {row['key']: owner_metadata(row) for row in read(paths['tracks'])}
    selected = read(OLD / 'whole_scan_inventory.json')['selected']
    assert len(selected) == 3
    references = next(row for row in read(paths['old_reference_inventory'])['rows']
                      if row['case'] == 'DS24-0013')
    historical = [references['target']] + references['other_same_family_raw_sources']
    historical_ids = [oid for row in historical for oid in row['observation_ids']]
    assert len(historical_ids) == len(set(historical_ids)) == 189
    accepted = {arm: set(ownership['coverage'][arm]['accepted_observation_ids']) for arm in ARMS}
    memberships = {}
    for arm in ARMS:
        coverage = ownership['coverage'][arm]
        curved = set(coverage['curved_observation_ids'])
        predictive = set(coverage['predictive_observation_ids'])
        postfit = set(coverage['postfit_only_observation_ids'])
        assert not curved & predictive
        assert curved | predictive | postfit == accepted[arm]
        memberships[arm] = {key: coverage[key] for key in
            ('curved_observation_ids', 'predictive_observation_ids',
             'postfit_only_observation_ids', 'accepted_observation_ids')}
        memberships[arm]['counts'] = dict(curved=len(curved), predictive=len(predictive),
                                          postfit_only=len(postfit), accepted=len(accepted[arm]),
                                          total_GLRT=len(observations))
    old_inventory_path = RESEARCH / 'ds24-nomination-information-r01/information/inventory.json'
    old_ranking_path = RESEARCH / 'ds24-nomination-information-r01/information/results.json'
    old_inventory = read(old_inventory_path)['sources']
    old_ranking = read(old_ranking_path)['rows']
    bindings[str(old_inventory_path)] = sha(old_inventory_path)
    bindings[str(old_ranking_path)] = sha(old_ranking_path)
    rows = []
    all_ids = []
    for row in selected:
        owner = tracks[row['component']]
        assert owner['receiver'] == 2
        assert owner['observation_ids'] == row['observation_ids']
        assert owner['times'] == row['times_s']
        assert native_matches(owner, observations)
        ids = set(owner['observation_ids'])
        assert len(ids) == len(owner['observation_ids'])
        assert not ids & set(historical_ids)
        assert not any(ids & accepted[arm] for arm in ARMS)
        all_ids.extend(owner['observation_ids'])
        old = next(x for x in old_inventory if x['case'] == 'DS24-0013' and x['component'] == row['component'])
        rank = next(x for x in old_ranking if x['case'] == 'DS24-0013' and x['component'] == row['component'])
        assert old['eligible'] and rank['status'] == 'complete'
        rows.append(dict(component=row['component'], native_metadata=owner,
            native_observation_metadata_exact=True, unused_in_both_arms=True,
            previous_exposure={key: old[key] for key in ('candidate_norad', 'alias',
                'archived_nomination_compatible', 'family_has_parent_likelihood', 'identity_qualified')} |
                {key: rank[key] for key in ('status', 'count_rank', 'duration_rank', 'information_rank')},
            previous_exposure_scope='archived response-selected rejected graph nominee and local conditional information ranking; no validated association'))
    assert len(all_ids) == len(set(all_ids)) == 124
    preparation_path = source / 'preparation_receipt.json'
    preparation = read(preparation_path)
    for name, expected in preparation['files_sha256'].items():
        path = source.parent / name
        assert sha(path) == expected
        bindings[str(path)] = expected
    bindings[str(preparation_path)] = sha(preparation_path)
    receipt = read(source / 'receipt.json')
    assert sha(source / 'bank.npz') == receipt['bank_sha256']
    assert sha(source / 'selected.tle') == receipt['latest_tle_sha256']
    assert sha(source / 'previous.tle') == receipt['previous_tle_sha256']
    elements = read(source / 'nominal_elements.json')
    assert len(elements) == receipt['candidate_count'] == 1487
    assert all(max(element['provenance']['element_epoch_utc_ns'],
                   element['provenance']['collected_utc_ns']) <= receipt['cutoff_utc_ns']
               for element in elements.values())
    input_receipt = read(source / 'input_receipt.json')
    assert sha(source / 'tracking.json') == input_receipt['tracking_sha256']
    public_input = Path(input_receipt['source_path'])
    try:
        digest = sha(public_input)
    except PermissionError:
        upstream = dict(current_bytes_verified=False, status='permission denied',
                        exported_copy_matches_original_source_digest=True)
    else:
        assert digest == input_receipt['source_sha256'].removeprefix('sha256:')
        bindings[str(public_input)] = digest
        upstream = dict(current_bytes_verified=True, status='exact',
                        exported_copy_matches_original_source_digest=True)
    assert input_receipt['tracking_sha256'] == input_receipt['source_sha256'].removeprefix('sha256:')
    result = dict(all_passed=True, rows=rows, baseline_membership=memberships,
        historical_RX1_owners=[{key: row[key] for key in ('component', 'observation_ids')} for row in historical],
        public_input_identity={key: input_receipt[key] for key in
            ('case', 'recording_id', 'recording_format', 'raw_authority_digest',
             'adapter', 'source_path', 'source_sha256', 'tracking_sha256')},
        upstream_public_input_access=upstream,
        causal_catalogue=dict(count=len(elements), cutoff_utc_ns=receipt['cutoff_utc_ns'],
            bank_sha256=receipt['bank_sha256'], all_element_epochs_and_collection_times_causal=True,
            element_60108_provenance=elements['60108']['provenance']),
        bindings=bindings, source_sha256=sha(__file__), seconds=time.monotonic()-began,
        new_owner_CFO_scores_read=False, new_CFO_comparisons=0,
        whitelisted_script_access_only=True, earlier_exploratory_access_incident='access_incident.json',
        position_fits=0, GPS_used=False, selection_changed=False)
    with (HERE / 'checks.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(all_passed=True, owners=len(rows), native_IDs=len(all_ids),
                         causal_catalogue=len(elements), bindings=len(bindings), seconds=result['seconds'])))


if __name__ == '__main__':
    main()
