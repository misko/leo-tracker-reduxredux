"""Read-only DS26 graph inventory against exact published ALGO03 v2 support.

Uses only sealed study artifacts, without replay, new inference, GPS, or TLE reads.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def published_ids(terminal, arm):
    selected = terminal.get('selected')
    if selected:
        return set(selected['arms'][arm]['associated_ids'])
    baseline = terminal['baseline']['arms'][arm]
    return {oid for t in baseline['gates']['tracks'] + baseline.get('linear_gates', [])
            for oid in t['observation_ids']}


def residual_stats(track, associated):
    kept = [(oid, t, v) for oid, t, v in zip(track['observation_ids'], track['times'], track['values'])
            if oid not in associated]
    if not kept:
        return None
    times = sorted(t for _, t, _ in kept)
    gaps = [b-a for a, b in zip(times, times[1:])]
    xbar = statistics.mean(t for _, t, _ in kept)
    ybar = statistics.mean(v for _, _, v in kept)
    xx = sum((t-xbar)**2 for _, t, _ in kept)
    slope = sum((t-xbar)*(v-ybar) for _, t, v in kept) / max(xx, 1e-12)
    linear_rms = (sum((v-ybar-slope*(t-xbar))**2 for _, t, v in kept)/len(kept))**0.5
    run_stats = {}
    for threshold in (2, 5, 10):
        runs = [[times[0]]]
        for t in times[1:]:
            if t-runs[-1][-1] > threshold:
                runs.append([])
            runs[-1].append(t)
        longest = max(runs, key=lambda r:(r[-1]-r[0],len(r)))
        run_stats.update({f'longest_run_gap_le_{threshold}s_span_s':longest[-1]-longest[0],
                          f'longest_run_gap_le_{threshold}s_points':len(longest),
                          f'runs_gap_le_{threshold}s':len(runs)})
    return dict(residual_points=len(kept), original_points=len(track['observation_ids']),
                published_associated_points=len(track['observation_ids'])-len(kept),
                wholly_unassociated=len(kept)==len(track['observation_ids']),
                start_s=times[0], end_s=times[-1], span_s=times[-1]-times[0],
                largest_gap_s=max(gaps, default=0), median_gap_s=statistics.median(gaps) if gaps else 0,
                gaps_over_2s=sum(g>2 for g in gaps), gaps_over_5s=sum(g>5 for g in gaps),
                unique_timestamps=len(set(times)),duplicate_timestamp_points=len(times)-len(set(times)),
                maximum_timestamp_multiplicity=max(Counter(times).values()), **run_stats,
                residual_linear_detrended_rms_hz=linear_rms,
                residual_observation_ids=[oid for oid, _, _ in kept])


def csv_write(path, rows):
    if not rows:
        return
    fields = [k for k, v in rows[0].items() if not isinstance(v, (list, dict))]
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def run(study, output):
    output.mkdir(parents=True, exist_ok=True)
    source_path = study/'candidate-final-inventory.json'
    source = read(source_path)
    rows = [r for r in source['rows'] if r['dataset']=='DS26']
    ranked, unavailable, unavailable_graphs, per_scan, hashes = [], [], [], [], {str(source_path): digest(source_path)}
    for entry in rows:
        case = entry['case']
        folder = study/'cases'/case
        if entry['state'] != 'complete':
            baseline = read(folder/'baseline-receipt.json')
            graph_path = folder/'algo02/inference/SCAN/tracks.json'
            obs_path = graph_path.with_name('observations.json')
            item = dict(case=case, state=entry['state'], baseline_state=baseline['state'],
                        reason=baseline.get('reason') or baseline.get('terminal', {}).get('reason'),
                        graph_path=str(graph_path) if graph_path.exists() else None,
                        observations_path=str(obs_path) if obs_path.exists() else None,
                        excluded_from_published_residual_rank=True)
            if graph_path.exists():
                tracks = read(graph_path)
                item.update(graph_tracks=len(tracks), total_GLRT=len(read(obs_path)),
                            maximum_raw_graph_span_s=max((max(t['times'])-min(t['times']) for t in tracks),default=0))
                item['raw_graph_tracks'] = [dict(track_index=i,component=t['key'],points=len(t['times']),
                    span_s=max(t['times'])-min(t['times']),start_s=min(t['times']),end_s=max(t['times']))
                    for i,t in enumerate(tracks)]
                unavailable_graphs.extend(dict(case=case,**t) for t in item['raw_graph_tracks'])
                hashes[str(graph_path)] = digest(graph_path)
                hashes[str(obs_path)] = digest(obs_path)
            unavailable.append(item)
            continue
        terminal_path = Path(entry['terminal_path'])
        assert digest(terminal_path)==entry['terminal_sha256'], case+' terminal hash changed'
        terminal = read(terminal_path)
        arm = terminal['selected_arm']
        associated = published_ids(terminal, arm)
        same_arms = published_ids(terminal, 'c0')==published_ids(terminal, 'fitted_c')
        assert same_arms, case+' c-arm published point memberships differ'
        descriptor_path = folder/'candidate-v2/recovery/snapshot/descriptor.json'
        if not descriptor_path.exists():
            descriptor_path = folder/'algo03/snapshot/descriptor.json'
        descriptor = read(descriptor_path)
        root = Path(descriptor['root'])/descriptor['case']
        tracks_path, observations_path = root/'tracks.json', root/'observations.json'
        tracks, observations = read(tracks_path), read(observations_path)
        all_ids = {o['observation_id'] for o in observations}
        assert len(all_ids)==len(observations), case+' duplicate observation IDs'
        assert associated <= all_ids, case+' published IDs absent from input'
        inventory_paths = sorted(folder.glob('candidate-v2/recovery/all-large*/**/inventory.json'))
        inventory_path = inventory_paths[0] if inventory_paths else None
        inventory = read(inventory_path) if inventory_path else None
        identities = inventory['job']['identities'] if inventory else [terminal['session_id']]
        source_inventory_ids = {r['track_index']:r['track_id'] for r in inventory['tracks']} if inventory else {}
        graph_ids = {oid for t in tracks for oid in t['observation_ids']}
        local = []
        for i, track in enumerate(tracks):
            assert len(track['observation_ids'])==len(track['times'])==len(track['values'])
            assert len(set(track['observation_ids']))==len(track['observation_ids']), case+' duplicate graph observation IDs'
            stats = residual_stats(track, associated)
            if stats is None:
                continue
            tid = hashlib.sha256(('\n'.join(identities)+'\n'+'\n'.join(sorted(track['observation_ids']))).encode()).hexdigest()[:20]
            if i in source_inventory_ids:
                assert tid==source_inventory_ids[i], case+' track identity mismatch'
            item = dict(case=case, track_id=tid, track_index=i, component=track['key'],
                        receiver=track['receiver'], channel=track['channel'],rf_hz=track['rf_hz'],
                        **stats, graph_polynomial_rms_hz=track['residual_rms_hz'],
                        graph_quality_status=track['quality_status'], graph_pieces=len(track['pieces']),
                        decision=terminal['decision'], selected_arm=arm, c_arm_memberships_identical=same_arms,
                        inventory_path=str(inventory_path) if inventory_path else None,
                        descriptor_path=str(descriptor_path),terminal_path=str(terminal_path),
                        tracks_path=str(tracks_path), observations_path=str(observations_path),
                        tracking_path=str(root/'tracking.json'))
            local.append(item)
        ranked.extend(local)
        replayed = set(inventory['policy'][arm]['proposed_associated_ids']) if inventory else set()
        summary = dict(case=case,decision=terminal['decision'],total_GLRT=len(all_ids),
                       published_associated=len(associated),residual_GLRT=len(all_ids-associated),
                       graph_tracks=len(tracks),residual_graph_tracks=len(local),
                       multi_point_residual_graph_tracks=sum(t['residual_points']>=2 for t in local),
                       residual_graph_unique_points=len(graph_ids-associated),
                       residual_outside_graph=len(all_ids-associated-graph_ids),
                       partial_residual_tracks=sum(not t['wholly_unassociated'] for t in local),
                       replay_owned_but_unpublished_residual_ids=len(replayed-associated),
                       maximum_residual_span_s=max((t['span_s'] for t in local),default=0),
                       inventory_path=str(inventory_path) if inventory_path else None,
                       descriptor_path=str(descriptor_path),terminal_path=str(terminal_path))
        per_scan.append(summary)
        for p in [terminal_path,descriptor_path,tracks_path,observations_path,inventory_path]:
            if p is not None:
                hashes[str(p)]=digest(p)
    ranked.sort(key=lambda r:(-r['span_s'],-r['residual_points'],r['case'],r['track_index']))
    for rank, row in enumerate(ranked,1):
        row['rank'] = rank
    unavailable_graphs.sort(key=lambda r:(-r['span_s'],-r['points'],r['case'],r['track_index']))
    fifth_span = ranked[4]['span_s']
    report = dict(schema='ds26-published-algo03-residual-inventory/v1',
        created_utc=datetime.now(timezone.utc).isoformat(),source=str(source_path),
        policy='Subtract exact selected v2 associated_ids; fallback subtracts baseline selected-arm gates.tracks and linear_gates IDs. Never subtract extra replay-only associations.',
        rank_definition='All graph tracks with at least one remaining original GLRT ID, descending first-to-last remaining-point duration, then residual point count. Singleton span is zero. Gaps retained; no interpolation counted.',
        unavailable_policy='Failed baseline graphs are inspected separately. With no completed published v2 support, they cannot truthfully be ranked as post-ALGO03 residuals.',
        continuity_policy='Duration is first-to-last remaining sample. Longest run fields split at adjacent timestamp gaps above an explicitly named 2, 5, or 10 seconds; they are sample-run summaries, not a claim of continuous RF coverage.',
        scope='All 159 fast DS26 entries in candidate-final-inventory; no GPS/TLE reads, no inference refit, no production write.',
        coverage=dict(DS26_entries=len(rows),complete_published_v2=len(per_scan),unavailable=len(unavailable),
                      unavailable_with_graphs=sum(u['graph_path'] is not None for u in unavailable),
                      total_GLRT=sum(s['total_GLRT'] for s in per_scan),
                      published_associated=sum(s['published_associated'] for s in per_scan),
                      residual_GLRT=sum(s['residual_GLRT'] for s in per_scan),
                      residual_graph_tracks=len(ranked),
                      original_graph_tracks=sum(s['graph_tracks'] for s in per_scan),
                      singleton_residual_graph_tracks=sum(r['residual_points']==1 for r in ranked),
                      residual_graph_unique_points=sum(s['residual_graph_unique_points'] for s in per_scan),
                      residual_outside_graph=sum(s['residual_outside_graph'] for s in per_scan),
                      wholly_unassociated_tracks=sum(r['wholly_unassociated'] for r in ranked),
                      partial_residual_tracks=sum(not r['wholly_unassociated'] for r in ranked),
                      residual_tracks_with_duplicate_timestamps=sum(r['duplicate_timestamp_points']>0 for r in ranked),
                      maximum_unavailable_raw_graph_span_s=unavailable_graphs[0]['span_s'],
                      unavailable_raw_graphs_exceeding_fifth_residual_span=sum(r['span_s']>fifth_span for r in unavailable_graphs),
                      completed_top5_unchanged_even_if_all_failed_graph_points_unassociated=all(r['span_s']<fifth_span for r in unavailable_graphs),
                      replay_owned_but_unpublished_residual_ids=sum(s['replay_owned_but_unpublished_residual_ids'] for s in per_scan)),
        tracks=ranked, per_scan=per_scan, unavailable=unavailable,source_sha256=hashes)
    (output/'inventory.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'top10.json').write_text(json.dumps(ranked[:10],indent=2)+'\n')
    (output/'unavailable.json').write_text(json.dumps(unavailable,indent=2)+'\n')
    (output/'unavailable_raw_graph_ranking.json').write_text(json.dumps(unavailable_graphs,indent=2)+'\n')
    csv_write(output/'residual_tracks.csv',ranked)
    csv_write(output/'top10.csv',ranked[:10])
    csv_write(output/'per_scan.csv',per_scan)
    csv_write(output/'unavailable_raw_graph_ranking.csv',unavailable_graphs)
    print(json.dumps(report['coverage'],indent=2))
    for r in ranked[:10]:
        print(r['rank'],r['case'],r['track_id'],r['track_index'],r['component'],
              f"{r['span_s']:.6f}s",r['residual_points'],f"gap {r['largest_gap_s']:.3f}s",r['wholly_unassociated'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,default=Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030'))
    parser.add_argument('--output',type=Path,default=Path(__file__).parent)
    args=parser.parse_args()
    run(args.study,args.output)
