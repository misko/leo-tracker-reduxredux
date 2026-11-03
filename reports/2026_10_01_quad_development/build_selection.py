"""Freeze 16 non-overlapping chronological quads using metadata only."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCES = {
    'DS9': ROOT/'reports/2026_09_28_ds9_post_ds8',
    'DS10': ROOT/'reports/2026_09_29_ds10_post_ds9/local',
    'DS11': ROOT/'reports/2026_09_30_ds11_post_ds10/local',
}
COUNTS = {'DS9': 6, 'DS10': 5, 'DS11': 5}
MAX_GAP_S = 180


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chronological_quads(captures, candidates, max_gap_s=MAX_GAP_S):
    """Break runs on inadmitted captures, hardware changes, overlap or long gaps."""
    by_id = {c['session_id']: c for c in captures}
    if len(by_id) != len(captures):
        raise ValueError('duplicate admitted session')
    ordered = sorted(candidates, key=lambda r: (r[1], r[3]))
    if len({r[3] for r in ordered}) != len(ordered):
        raise ValueError('duplicate candidate session')
    if not set(by_id) <= {r[3] for r in ordered}:
        raise ValueError('admitted capture absent from candidate inventory')
    run, blocks, breaks = [], [], []
    for row in ordered:
        capture = by_id.get(row[3])
        if capture is None:
            breaks.append(dict(session_id=row[3], reason='not_admitted_to_source_dataset'))
            run = []
            continue
        if row[1] != capture['capture_start_utc_ns'] or row[2] != capture['radio_id']:
            raise ValueError('candidate/manifest identity mismatch')
        if capture['capture_end_utc_ns'] <= capture['capture_start_utc_ns']:
            raise ValueError('invalid capture interval')
        if run:
            previous = run[-1]
            gap = (capture['capture_start_utc_ns']-previous['capture_end_utc_ns'])/1e9
            if (not 0 <= gap <= max_gap_s or
                    capture['radio_id'] != previous['radio_id'] or
                    capture['receiver_ids'] != previous['receiver_ids']):
                breaks.append(dict(session_id=row[3], reason='gap_or_hardware_boundary', gap_s=gap))
                run = []
        run.append(capture)
        if len(run) == 4:
            blocks.append(run)
            run = []
    return blocks, breaks


def spread(blocks, count):
    if count < 2 or len(blocks) < count:
        raise ValueError('insufficient quads or unsupported count')
    return [blocks[i*(len(blocks)-1)//(count-1)] for i in range(count)]


def evaluation_units(block_id, units):
    if len(units) != 4 or len(set(units)) != 4:
        raise ValueError('quad must contain four distinct scans')
    return ([dict(unit_id=f'{block_id}-S{i+1}', block_id=block_id, size=1, scans=[u])
             for i, u in enumerate(units)] +
            [dict(unit_id=f'{block_id}-D{i+1}', block_id=block_id, size=2, scans=units[2*i:2*i+2])
             for i in range(2)] +
            [dict(unit_id=f'{block_id}-Q', block_id=block_id, size=4, scans=units)])


def build():
    old_path = ROOT/'reports/2026_09_30_gaussian_sum_64_scan/selection.json'
    old = json.loads(old_path.read_text())
    old_sessions = {r['session_id'] for rows in old['selected'].values() for r in rows}
    bindings = {str(old_path.relative_to(ROOT)): digest(old_path)}
    blocks, units, selected_captures, inventories = [], [], [], {}
    for dataset, directory in SOURCES.items():
        manifest_path, candidate_path = directory/'manifest.json', directory/'candidate-index.json'
        if digest(manifest_path) != old['authorities'][dataset]['sha256']:
            raise ValueError('source manifest changed from original benchmark')
        manifest = json.loads(manifest_path.read_text())
        index = json.loads(candidate_path.read_text())
        if (index['cutoff'] != manifest['inventory_cutoff_utc_ns'] or
                index['lower'] != manifest['after_parent_capture_end_utc_ns']):
            raise ValueError('candidate inventory boundaries differ from manifest')
        captures = sorted(manifest['captures'], key=lambda r: (r['capture_start_utc_ns'], r['session_id']))
        ranks = {r['session_id']: i+1 for i, r in enumerate(captures)}
        eligible, breaks = chronological_quads(captures, index['candidates'])
        inventories[dataset] = dict(admitted_scans=len(captures), eligible_nonoverlapping_quads=len(eligible), breaks=breaks)
        for path in (manifest_path, candidate_path):
            bindings[str(path.relative_to(ROOT))] = digest(path)
        for number, quad in enumerate(spread(eligible, COUNTS[dataset]), 1):
            block_id = f'{dataset}-B{number:02d}'
            ids = [f'{dataset}-F{ranks[c["session_id"]]:03d}' for c in quad]
            block = dict(block_id=block_id, dataset=dataset, scans=ids,
                sessions=[c['session_id'] for c in quad],
                capture_start_utc_ns=quad[0]['capture_start_utc_ns'],
                capture_end_utc_ns=quad[-1]['capture_end_utc_ns'],
                span_s=(quad[-1]['capture_end_utc_ns']-quad[0]['capture_start_utc_ns'])/1e9,
                gaps_s=[(b['capture_start_utc_ns']-a['capture_end_utc_ns'])/1e9 for a,b in zip(quad,quad[1:])],
                pose_continuity='not_established_by_dataset_metadata',
                matched_prefix_units=[f'{block_id}-S1', f'{block_id}-D1', f'{block_id}-Q'])
            blocks.append(block)
            units.extend(evaluation_units(block_id, ids))
            for unit, capture in zip(ids, quad):
                selected_captures.append(dict(capture, unit_id=unit, dataset=dataset,
                    block_id=block_id, original_64_member=capture['session_id'] in old_sessions))
    assert len(blocks) == 16 and len(selected_captures) == 64
    assert len({c['session_id'] for c in selected_captures}) == 64
    assert len({c['manifest_sha256'] for c in selected_captures}) == 64
    assert Counter(u['size'] for u in units) == {1:64, 2:32, 4:16}
    for path in (Path(__file__), HERE/'test_selection.py', HERE/'PROTOCOL.md'):
        bindings[str(path.relative_to(ROOT))] = digest(path)
    return dict(schema='quad-development-selection/v1', status='membership_frozen_inference_not_run',
        role='development; not untouched validation',
        selection_method='Disjoint chronological runs of four; reject missing source candidates and gaps outside [0,180]s; floor-spaced eligible blocks per dataset; no fit scores or GPS used.',
        block_counts=COUNTS, max_inter_scan_gap_s=MAX_GAP_S,
        source_sha256=bindings, inventories=inventories,
        blocks=blocks, captures=selected_captures, evaluation_units=units,
        overlap_original64=sum(c['original_64_member'] for c in selected_captures),
        exclusions='DS12 reserved; no cross-dataset blocks; no backfilling after inference failures',
        preparation='Source manifests bind complete public analysis products. New observation/orbit input admission and stationary-site audit pending; raw IQ not copied or read.')


def main():
    result = build()
    output = HERE/'selection.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(blocks=len(result['blocks']), scans=len(result['captures']),
                          evaluations=len(result['evaluation_units']), overlap_original64=result['overlap_original64'])))


if __name__ == '__main__':
    main()
