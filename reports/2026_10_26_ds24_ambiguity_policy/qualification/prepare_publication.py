"""Compact publication index; full frozen artifacts remain untouched locally."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return dict(path=str(path), relative_path=str(path.relative_to(HERE)),
                bytes=path.stat().st_size, sha256=sha(path))


if __name__ == '__main__':
    metadata_path = HERE / 'metadata.json'
    original = json.loads(metadata_path.read_text())
    compact = dict(source=record(metadata_path), complete_target_native_IDs_retained=True,
        targets=original['targets'], witness_availability={})
    for case, availability in original['witness_availability'].items():
        selected = availability['selected']
        rows = []
        for row in availability['all_other_owner_metadata']:
            output = {key: value for key, value in row.items() if key != 'observation_ids'}
            ids = row['observation_ids']
            output.update(native_ID_count=len(ids), native_ID_json_sha256=hashlib.sha256(
                json.dumps(ids, separators=(',', ':')).encode()).hexdigest())
            rows.append(output)
        compact['witness_availability'][case] = dict(selected=selected,
            all_other_owner_metadata=rows, selection_independent_of_candidate_columns=True,
            same_family_validated=False, scored_in_this_branch=False)
    destination = HERE / 'metadata_compact.json'
    destination.write_text(json.dumps(compact, indent=2) + '\n')
    top = {'PROTOCOL.md', 'FINDINGS.md', 'protocol.json', 'metadata_compact.json',
           'preparation.json', 'execution.json', 'execution_started.json',
           'screen_receipt.json', 'c0_execution.json', 'fitted_c_execution.json',
           'RF_seal.json', 'test_receipt.json', 'test_attempt01.json', 'test_attempt02.json'}
    selected, external = [], []
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or any(z in path.parts for z in ('__pycache__', '.pytest_cache')):
            continue
        relative = path.relative_to(HERE)
        if path.name == 'lean_publication.json':
            continue
        publish = (len(relative.parts) == 1 and (path.name in top or path.suffix == '.py')
                   or relative.parts[0] in ('report', 'preparation01')
                   or relative.parts[0].startswith('DS24-') and
                   (path.name in ('entry.json', 'original_trace.json')
                    or path.name.endswith(('_result.json', '_failure.json', '_adequacy_checkpoint.json'))))
        (selected if publish else external).append(record(path))
    manifest = dict(schema='qualification-lean-publication/v1',
        published=selected, local_external=external,
        published_file_count=len(selected), published_bytes=sum(q['bytes'] for q in selected),
        full_local_metadata=record(metadata_path),
        standalone_numerical_replay=False, omitted_arrays_or_ledgers_required_for_replay=True,
        scientific_membership_and_values_unchanged=True,
        note='RF seal binds the full local experiment; small Git report omits hash-inventoried arrays, complete catalogue screens, support/checkpoint ledgers and full cavity/native-owner metadata.')
    (HERE / 'lean_publication.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({key: manifest[key] for key in ('published_file_count', 'published_bytes')}))
