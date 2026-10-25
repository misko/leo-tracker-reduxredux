"""Read-only replay of the historical CH4 salvage duration prerequisite."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
INPUT = Path('/srv/bulk/leo/research/ds25-20261024/DS24-0013')
KEY = 'DS24-0013-RX2-CH4-T000-RF11690312500.000000'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = REPO / 'tools/run_algo01_ds23_sample.py'
    paths = [source, INPUT/'tracks.json', INPUT/'result.json', Path(__file__)]
    hashes = {str(p): sha(p) for p in paths}
    result = json.loads((INPUT/'result.json').read_text())
    assert sha(source) == result['source_sha256']
    track = next(t for t in json.loads((INPUT/'tracks.json').read_text()) if t['key'] == KEY)
    history = next(r for r in result['trims'] if r['component'] == KEY)
    tree = ast.parse(source.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'selected_supports')
    # Execute only the recorded pure index-list function, not its CLI/module.
    scope = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
    assert 't[b - 1] - t[a] >= 20 and raw_curvature' in source.read_text()
    times = track['times']
    rows = [dict(start_index=a, stop_index=b, count=b-a,
                 span_s=times[b-1]-times[a], passes_duration=times[b-1]-times[a]>=20)
            for a,b in scope['selected_supports'](len(times))]
    # These are A's metadata-defined thirds/half cuts, not fitted cutoffs.
    proposed = []
    for cut in (14, 21, 29):
        spans = [times[cut-1]-times[0], times[-1]-times[cut]]
        proposed.append(dict(cut_after_count=cut, gap_times_s=times[cut-1:cut+1],
                             prefix_duration_s=spans[0], suffix_duration_s=spans[1],
                             prefix_passes_old_duration=spans[0]>=20,
                             suffix_passes_old_duration=spans[1]>=20))
    summary = dict(component=KEY, input_sha256=hashes,
        historical_runner_hash_matches=True, native_points=len(times),
        archived_quality_status=track['quality_status'],
        archived_diagnostics=track['diagnostics'],
        original_index_support_count=len(rows),
        duration_eligible_support_count=sum(r['passes_duration'] for r in rows),
        historical_after_all_support_gates=history,
        original_duration_threshold_s=20,
        proposed_metadata_cuts=proposed, support_duration_replay=rows,
        interpretation='The apparent roughly 14-second prefix cannot enter historical curved salvage. Duration passing is only necessary, not sufficient; the historical runner additionally requires raw_curvature. This does not authorize changing that gate or calibrating from a short/linear piece.',
        new_curve_fits=0, new_orbit_scores=0, new_position_fits=0, GPS_used=False,
        historical_exact_gate_for_whole_track='not reconstructed from intermediate metrics')
    assert len(rows)==63 and sum(r['passes_duration'] for r in rows)==27
    assert history['supports_tested']==15 and history['selected'] is None
    assert hashes=={str(p):sha(p) for p in paths}
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT/'summary.json').open('x') as stream:
        json.dump(summary, stream, indent=2);stream.write('\n')
    seal = {str(p):sha(p) for p in [Path(__file__), ROOT/'summary.json']}
    with (ROOT/'seal.json').open('x') as stream:
        json.dump(seal, stream, indent=2);stream.write('\n')
    print(json.dumps({k:summary[k] for k in ['native_points','original_index_support_count','duration_eligible_support_count','historical_after_all_support_gates','proposed_metadata_cuts']}))


if __name__ == '__main__':
    main()
