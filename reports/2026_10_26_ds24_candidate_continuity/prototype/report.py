"""Evaluate sealed RF paths against exposed synthetic truth; saved numbers only."""
import csv
import json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import experiment as e
import continuity as c

HERE = Path(__file__).resolve().parent
OUT = HERE/'report'


def table(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w') as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)


def labels(candidate, source, time_s):
    f_errors = [float(c.circular(candidate['cfo_hz']-(s['cfo0']+s['rate']*time_s), c.SETTINGS['cfo_period_hz'])) for s in source]
    p_errors = [float(c.circular(candidate['global_epoch_samples']-s['epoch'], e.RATE/750)) for s in source]
    near_cfo = [i for i, v in enumerate(f_errors) if abs(v) <= 450.]
    near_joint = [i for i, v in enumerate(f_errors) if abs(v) <= 450. and abs(p_errors[i]) <= 3.]
    def name(ix): return ('A', 'B')[ix[0]] if len(ix) == 1 else ('ambiguous' if ix else 'unmatched')
    return dict(cfo_label=name(near_cfo), joint_label=name(near_joint),
                cfo_errors_hz=f_errors, epoch_errors_samples=p_errors, source_hits=near_joint)


def main():
    OUT.mkdir(exist_ok=False)
    rf = json.loads((HERE/'RF_seal.json').read_text())
    for p, digest in rf['files'].items():
        if e.sha(p) != digest: raise ValueError('RF artifact changed: '+p)
    port = json.loads((HERE/'prepared/synthetic_rows.json').read_text())
    execution = json.loads((HERE/'execution.json').read_text())
    by_name = {p['name']:p for p in port['episodes']}
    # Access source labels only AFTER the response-only RF seal is verified.
    truth = {}
    for episode in port['episodes']:
        for w in episode['windows']:
            visit = round(w['window_start_counter']/e.RATE)
            truth[(episode['name'], w['window_id'])] = json.loads((e.OLD/'slots'/f"{episode['name']}_{visit:02}.json").read_text())['sources']
    method_rows = []; path_rows = []; selected_rows = []; selections = {}
    for record in execution['records']:
        base = dict(episode=record['episode'], receiver=int(record['receiver_id']), method=record['method'], status=record['status'])
        if record['status'] != 'complete':
            method_rows.append(base); continue
        episode = by_name[record['episode']]
        windows = [w for w in episode['windows'] if str(w['receiver_id']) == record['receiver_id']]
        byid = {n['candidate_id']:(w,n) for w in windows for n in w['candidates']}
        byobs = {w['observation_id']:w for w in windows}
        selected = json.loads(Path(record['selection_file']).read_text())
        graphs = json.loads(Path(record['graph_file']).read_text())
        selections[(record['episode'], record['receiver_id'], record['method'])] = selected
        all_hits = set(); selected_hits = set(); graph_hits = set(); graph_windows = set()
        all_input = sum(len(w['candidates']) for w in windows)
        for w in windows:
            for n in w['candidates']:
                lab = labels(n, truth[(record['episode'], w['window_id'])], w['time_s'])
                all_hits.update((w['window_id'], j) for j in lab['source_hits'])
        graph_count = 0; graph_assigned = 0; quality = Counter(); mixed_cfo = 0; mixed_joint = 0
        for pi, (path, graph) in enumerate(zip(selected['paths'], graphs)):
            path_cfo = Counter(); path_joint = Counter(); rank_counts = Counter(); margins = []
            for n in path['nodes']:
                w, candidate = byid[n['candidate_id']]
                lab = labels(candidate, truth[(record['episode'], w['window_id'])], w['time_s'])
                path_cfo[lab['cfo_label']] += 1; path_joint[lab['joint_label']] += 1
                selected_hits.update((w['window_id'], j) for j in lab['source_hits'])
                rank_counts[candidate['candidate_rank']] += 1
                margins.append(candidate['margin']/max(x['margin'] for x in w['candidates']))
                selected_rows.append(dict(**base, path=pi, window_id=w['window_id'], candidate_id=n['candidate_id'],
                    time_s=w['time_s'], candidate_rank=candidate['candidate_rank'], margin=candidate['margin'],
                    cfo_hz=candidate['cfo_hz'], global_epoch_samples=candidate['global_epoch_samples'],
                    cfo_label=lab['cfo_label'], joint_label=lab['joint_label'],
                    CFO_error_A_Hz=lab['cfo_errors_hz'][0], CFO_error_B_Hz=lab['cfo_errors_hz'][1],
                    epoch_error_A_samples=lab['epoch_errors_samples'][0], epoch_error_B_samples=lab['epoch_errors_samples'][1]))
            mixed_cfo += path_cfo['A'] > 0 and path_cfo['B'] > 0
            mixed_joint += path_joint['A'] > 0 and path_joint['B'] > 0
            path_rows.append(dict(**base, path=pi, points=len(path['nodes']), score=path['score'],
                cfo_A=path_cfo['A'], cfo_B=path_cfo['B'], cfo_ambiguous=path_cfo['ambiguous'], cfo_unmatched=path_cfo['unmatched'],
                joint_A=path_joint['A'], joint_B=path_joint['B'], joint_ambiguous=path_joint['ambiguous'], joint_unmatched=path_joint['unmatched'],
                median_margin_ratio=float(np.median(margins)), rank_histogram=json.dumps(dict(rank_counts)),
                graph_tracks=len(graph['tracks']), graph_assigned_candidate_hypotheses=graph['assigned']))
            graph_count += len(graph['tracks']); graph_assigned += graph['assigned']
            graph_byid = {r['observation_id']:r for r in graph['rows']}
            for track in graph['tracks']:
                quality[track['quality_status']] += 1
                for oid in track['observation_ids']:
                    row = graph_byid[oid]; w, n = byid[row['candidate_id']]
                    graph_windows.add(w['window_id'])
                    lab = labels(n, truth[(record['episode'], w['window_id'])], w['time_s'])
                    graph_hits.update((w['window_id'], j) for j in lab['source_hits'])
        used = Counter(n['window_id'] if 'window_id' in n else byid[n['candidate_id']][0]['window_id']
                       for p in selected['paths'] for n in p['nodes'])
        method_rows.append(dict(**base, receiver_windows=len(windows), physical_acquisitions=len({w['physical_acquisition_id'] for w in windows}),
            candidate_pool=all_input, RF_path_hypotheses=len(selected['paths']),
            selected_candidate_hypotheses=selected['candidate_hypotheses_selected'],
            unique_selected_windows=selected['unique_receiver_windows'], shared_windows=sum(n > 1 for n in used.values()),
            source_slots=len(windows)*2, all_candidate_joint_source_coverage=len(all_hits),
            selected_joint_source_coverage=len(selected_hits), graph_joint_source_coverage=len(graph_hits),
            RF_paths_mixed_CFO_proximity=mixed_cfo, RF_paths_mixed_joint_proximity=mixed_joint,
            graph_tracks=graph_count, graph_candidate_assignments=graph_assigned,
            unique_graph_windows=len(graph_windows), graph_no_structure_detected=quality['no_structure_detected'],
            graph_insufficient_support=quality['insufficient_support'], graph_structure_flagged=quality['structure_flagged']))
    table(OUT/'methods_by_lane.csv', method_rows); table(OUT/'path_diagnostics.csv', path_rows)
    table(OUT/'selected_hypotheses.csv', selected_rows)
    aggregates = []
    methods = ('original_winners', 'cfo_only', 'epoch_cfo')
    keys = ['receiver_windows', 'candidate_pool', 'RF_path_hypotheses', 'selected_candidate_hypotheses',
        'unique_selected_windows', 'shared_windows', 'source_slots', 'all_candidate_joint_source_coverage',
        'selected_joint_source_coverage', 'graph_joint_source_coverage', 'RF_paths_mixed_CFO_proximity',
        'RF_paths_mixed_joint_proximity', 'graph_tracks', 'graph_candidate_assignments', 'unique_graph_windows',
        'graph_no_structure_detected', 'graph_insufficient_support', 'graph_structure_flagged']
    for episode in port['episodes']:
        for method in methods:
            rows = [r for r in method_rows if r['episode'] == episode['name'] and r['method'] == method and r['status'] == 'complete']
            aggregates.append(dict(episode=episode['name'], method=method, **{k:sum(r[k] for r in rows) for k in keys}))
    table(OUT/'comparison.csv', aggregates)
    titles = {'original_winners':'Original winners', 'cfo_only':'CFO-only paths', 'epoch_cfo':'Epoch + CFO paths'}
    for quantity in ('cfo', 'epoch'):
        fig, axes = plt.subplots(3, 4, figsize=(16, 10), layout='constrained')
        for col, episode in enumerate(port['episodes']):
            name = episode['name']; windows = [w for w in episode['windows'] if w['receiver_id'] == '0']
            for ri, method in enumerate(methods):
                ax = axes[ri, col]
                for w in windows:
                    tr = truth[(name,w['window_id'])]
                    for n in w['candidates']:
                        value = float(c.circular(n['cfo_hz']-(tr[0]['cfo0']+tr[0]['rate']*w['time_s']), c.SETTINGS['cfo_period_hz'])) if quantity == 'cfo' else float(c.circular(n['global_epoch_samples']-tr[0]['epoch'], e.RATE/750))
                        ax.scatter(w['time_s'], value, s=9, color='.8', zorder=1)
                for rx, marker in (('0', 'o'), ('1', 'x')):
                    result = selections[(name,rx,method)]
                    rx_windows = {n['candidate_id']:w for w in episode['windows'] if w['receiver_id'] == rx for n in w['candidates']}
                    for pi, path in enumerate(result['paths']):
                        xs=[]; ys=[]
                        for node in path['nodes']:
                            w=rx_windows[node['candidate_id']]; tr=truth[(name,w['window_id'])]
                            xs.append(w['time_s'])
                            ys.append(float(c.circular(node['cfo_hz']-(tr[0]['cfo0']+tr[0]['rate']*w['time_s']), c.SETTINGS['cfo_period_hz'])) if quantity == 'cfo' else float(c.circular(node['global_epoch_samples']-tr[0]['epoch'],e.RATE/750)))
                        ax.plot(xs, ys, color=('#1769a3','#b15d29')[pi%2], marker=marker,
                            markersize=3, linewidth=1, alpha=.8)
                ts=np.arange(16)+.01
                ax.axhline(0,color='black',linestyle='--',linewidth=.8)
                if quantity == 'cfo':
                    ax.plot(ts,3000-400*ts,color='.4',linestyle=':',linewidth=1)
                else:
                    ax.axhline(0 if name.startswith('coincident') else 684,color='.4',linestyle=':',linewidth=1)
                ax.set_yscale('symlog',linthresh=300 if quantity=='cfo' else 3)
                ax.grid(alpha=.2); ax.set_title(titles[method] if ri else name.replace('_sampled_deployed',' · sampled').replace('_continuous',' · continuous')+'\n'+titles[method],fontsize=9)
                if col == 0: ax.set_ylabel('Circular CFO − A (Hz)' if quantity=='cfo' else 'Circular epoch − A (samples)')
                if ri == 2: ax.set_xlabel('Synthetic seconds')
        fig.legend(handles=[Line2D([],[],color='#1769a3',label='Path hypothesis 1'),
            Line2D([],[],color='#b15d29',label='Path hypothesis 2'),
            Line2D([],[],marker='o',linestyle='',color='black',label='RX0 (RX1: ×)'),
            Line2D([],[],color='black',linestyle='--',label='Known A (evaluation only)'),
            Line2D([],[],color='.4',linestyle=':',label='Known B (evaluation only)')],loc='outside upper center',ncol=5,fontsize=9)
        fig.supxlabel('Paths may reuse correlated alternatives from one window. No physical source count or identity is inferred.',fontsize=10)
        fig.savefig(OUT/(quantity+'_paths.png'),dpi=160);plt.close(fig)
    fig, axes = plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax, key, title, denominator in ((axes[0],'unique_selected_windows','Unique receiver-window coverage',32),
                                         (axes[1],'selected_joint_source_coverage','Known-source proximity coverage (not identity)',64)):
        for j, method in enumerate(methods):
            rows=[r for r in aggregates if r['method']==method]
            ax.bar(np.arange(4)+(j-1)*.24,[r[key] for r in rows],width=.23,label=titles[method])
        ax.set_xticks(range(4),[e['name'].replace('_sampled_deployed','\nsampled').replace('_continuous','\ncontinuous') for e in port['episodes']],fontsize=9)
        ax.set_ylim(0,denominator+3);ax.axhline(denominator,color='.6',linestyle=':');ax.set_title(title)
        ax.set_ylabel('Unique slots');ax.grid(axis='y',alpha=.2)
    fig.legend(loc='outside upper center',ncol=3)
    fig.savefig(OUT/'coverage.png',dpi=170);plt.close(fig)
    summary=dict(RF_seal_sha256=e.sha(HERE/'RF_seal.json'),protocol_sha256=e.sha(HERE/'protocol.json'),
        execution=execution,comparisons=aggregates,path_diagnostics=path_rows,
        physically_qualified_sources=0,new_detector_calls=0,no_position_or_identity_claim=True)
    e.write(OUT/'summary.json',summary)
    files=[Path(__file__),*[p for p in OUT.iterdir() if p.is_file()]]
    e.write(OUT/'seal.json',dict(files={str(p):e.sha(p) for p in files},RF_seal_sha256=e.sha(HERE/'RF_seal.json')))
    print(json.dumps(aggregates,indent=2))


if __name__=='__main__': main()
