"""Summarize terminal recorded replay JSON; no IQ, detector or refiner calls."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT = HERE / 'report02'


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def table(path, rows):
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    if OUT.exists():
        raise FileExistsError('preserve the original report')
    for path, expected in load(HERE / 'RF_seal.json')['files'].items():
        assert sha(path) == expected, path
    OUT.mkdir()
    result = load(HERE / 'results.json')
    requests = {r['request_id']: r for r in load(HERE.parent / 'influence/window_requests.json')}
    rows = []
    for record in result['records']:
        request = requests[record['request_id']]
        row = dict(request_id=record['request_id'], case=record['case'], role=record['role'],
                   owner=record['owner'], native_id=request['native_observation_id'],
                   time_quantile=request['time_quantile'], time_s=request['probe']['time_s'],
                   receiver=request['probe']['receiver_id'] + 1, channel=request['probe']['channel'],
                   status=record['status'], error=record.get('error', ''),
                   candidate_parity=False, returned_candidates_both_receivers=0, archived_candidates_checked=0,
                   old_acquired_cfo_hz=None, old_residual_cfo_hz=None, old_final_cfo_hz=None,
                   refined_final_cfo_hz=None, delta_hz=None, old_exact=None, old_control=None,
                   refined_exact=None, refined_control=None, delta_margin=None,
                   frequency_qualified=False, margin_qualified=False, boundary=None)
        if record['status'] == 'complete':
            f = record['refinement']
            row.update(candidate_parity=all(v['all_passed'] for v in record['candidate_parity'].values()),
                       returned_candidates_both_receivers=sum(len(r['candidates']) for r in record['full_original_replay_result']['receivers']),
                       archived_candidates_checked=sum(sum(c['field'] == 'candidate_rank' for c in v['checks']) for v in record['candidate_parity'].values()),
                       old_acquired_cfo_hz=f['acquired_cfo_hz'], old_residual_cfo_hz=f['old_residual_cfo_hz'],
                       old_final_cfo_hz=f['old_tracking_cfo_hz'], refined_final_cfo_hz=f['corrected_tracking_cfo_hz'],
                       delta_hz=record['correction_delta_hz'], old_exact=f['old_exact_score'], old_control=f['old_control_score'],
                       refined_exact=f['corrected_exact_score'], refined_control=f['corrected_control_score'],
                       delta_margin=f['corrected_margin'] - (f['old_exact_score'] - f['old_control_score']),
                       frequency_qualified=f['numerical_frequency_qualified'], margin_qualified=f['numerical_margin_qualified'],
                       boundary=f['exact']['boundary'] or f['control']['boundary'])
        rows.append(row)
    table(OUT / 'all_slots.csv', rows)
    pairs = []
    for owner in dict.fromkeys(r['owner'] for r in rows):
        owner_rows = sorted([r for r in rows if r['owner'] == owner], key=lambda r: r['time_s'])
        complete = len(owner_rows) == 2 and all(r['status'] == 'complete' for r in owner_rows)
        early, late = owner_rows
        pairs.append(dict(case=early['case'], role=early['role'], owner=owner,
                          complete_two_window_pair=complete, early_time_s=early['time_s'], late_time_s=late['time_s'],
                          early_delta_hz=early['delta_hz'], late_delta_hz=late['delta_hz'],
                          late_minus_early_delta_hz=late['delta_hz'] - early['delta_hz'] if complete else None))
    table(OUT / 'owner_delta_pairs.csv', pairs)
    complete_rows = [r for r in rows if r['status'] == 'complete']
    parity_errors = [c.get('error', 0) for r in result['records'] for p in r.get('candidate_parity', {}).values() for c in p['checks']]
    summary = dict(declared_slots=len(rows), completed=len(complete_rows), failed=sum(r['status'] == 'failed' for r in rows),
                   not_attempted=sum(r['status'] == 'not_attempted' for r in rows), complete_owner_pairs=sum(p['complete_two_window_pair'] for p in pairs),
                   paired_detector_calls=result['paired_detector_calls'], cumulative_worker_seconds=result['cumulative_worker_seconds'],
                   returned_detector_candidates=sum(r['returned_candidates_both_receivers'] for r in rows),
                   archived_export_candidates_checked=sum(r['archived_candidates_checked'] for r in rows),
                   full_candidate_parity_pass=all(r['candidate_parity'] for r in complete_rows),
                   maximum_candidate_parity_float_error=max(parity_errors, default=None),
                   old_residual_zero=sum(r['old_residual_cfo_hz'] == 0 for r in complete_rows),
                   frequency_qualified=sum(r['frequency_qualified'] for r in rows), margin_qualified=sum(r['margin_qualified'] for r in rows),
                   boundary_hits=sum(bool(r['boundary']) for r in rows),
                   minimum_delta_hz=min((r['delta_hz'] for r in complete_rows), default=None),
                   maximum_delta_hz=max((r['delta_hz'] for r in complete_rows), default=None),
                   real_CFO_truth_available=False, position_fit_performed=False,
                   sparse_two_windows_do_not_determine_whole_owner_correction=True,
                   input_results_sha256=sha(HERE / 'results.json'))
    dump(OUT / 'summary.json', summary)

    colors = ['#D55E00' if r['role'] == 'target' else '#0072B2' for r in rows]
    labels = [f"{r['case'][-4:]} {r['role']} {int(r['time_quantile']*100)}%" for r in rows]
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    for axis in axes:
        axis.set_yticks(range(len(rows)), labels)
        axis.invert_yaxis()
        axis.axvline(0, color='.4', lw=.8)
        axis.grid(axis='x', alpha=.2)
    axes[0].barh(range(len(rows)), [r['delta_hz'] or 0 for r in rows], color=colors)
    axes[0].set(xlabel='Refined minus original CFO (Hz)', title='Local continuous refinement changes recorded CFO')
    for i, row in enumerate(rows):
        if row['status'] == 'complete':
            x = row['delta_hz']
            axes[0].annotate(f'{x:+.1f}', (x, i), xytext=(4 if x >= 0 else -4, 0),
                             textcoords='offset points', va='center', ha='left' if x >= 0 else 'right', fontsize=9)
        else:
            axes[0].text(0, i, row['status'], va='center')
    axes[0].margins(x=.18)
    axes[1].barh(range(len(rows)), [1e3 * (r['delta_margin'] or 0) for r in rows], color=colors)
    axes[1].set(xlabel='Change in exact-minus-control score (× 0.001)', title='Both scores refined; margin can decrease')
    fig.suptitle('Eight original accepted-owner windows: exact replay before local refinement\nNumerical qualification is not recorded-frequency truth or localization validation', fontsize=12)
    fig.savefig(OUT / 'cfo_refinement.png', dpi=170)
    fig.savefig(OUT / 'cfo_refinement.pdf')
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True, sharey=True)
    for axis, pair in zip(axes.flat, pairs):
        owner_rows = sorted([r for r in rows if r['owner'] == pair['owner']], key=lambda r: r['time_s'])
        axis.axhline(0, color='.4', lw=.8)
        axis.grid(alpha=.2)
        axis.set(title=f"{pair['case']} {pair['role']}: RX{owner_rows[0]['receiver']} CH{owner_rows[0]['channel']}",
                 xlabel='Original scan midpoint time (s)', ylabel='Refined minus original CFO (Hz)')
        for row in owner_rows:
            if row['status'] == 'complete':
                axis.scatter(row['time_s'], row['delta_hz'], color='#D55E00' if row['role'] == 'target' else '#0072B2', s=65)
                axis.annotate(f"{int(row['time_quantile']*100)}%: {row['delta_hz']:+.1f} Hz", (row['time_s'], row['delta_hz']),
                              xytext=(0, 10), textcoords='offset points', ha='center', fontsize=9)
        if pair['complete_two_window_pair']:
            axis.text(.03, .04, f"Late − early change: {pair['late_minus_early_delta_hz']:+.1f} Hz", transform=axis.transAxes, fontsize=9)
        else:
            axis.text(.03, .04, 'Incomplete pair; no paired summary', transform=axis.transAxes)
        axis.margins(x=.35)
        axis.set_ylim(-100, 110)
    fig.suptitle('Two fixed time quantiles per complete owner\nSparse changes vary within owners; no interpolation or whole-owner correction is applied', fontsize=12)
    fig.savefig(OUT / 'owner_delta_pairs.png', dpi=170)
    fig.savefig(OUT / 'owner_delta_pairs.pdf')
    plt.close(fig)
    dump(OUT / 'seal.json', dict(schema='recorded8-saved-output-report/v1', source_sha256=sha(__file__),
                                RF_seal_sha256=sha(HERE / 'RF_seal.json'), saved_output_only=True,
                                files={str(p.relative_to(HERE)): sha(p) for p in sorted(OUT.iterdir()) if p.is_file()}))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
