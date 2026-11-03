"""Truthful extension inventory and processing status; never infers completion."""
import csv
import html
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
WORK = Path('/srv/bulk/leo/receiver-sky-82-20261005')


def inspect_scan(meta):
    label = meta['label']
    folder = WORK/'inputs'/label
    row = {k: meta[k] for k in ('label','session_id','sample_rate_hz','capture_utc','selection_rank')}
    row.update(exported=False, orbit_ready=False, refined=False, calibrated=False, associated=False, sky_ready=False,
               candidates=0, passing_windows=0, scheduled_receiver_probes=0, refined_candidates=0,
               failed_refinements=None, no_retained_iq_events=None, calibration_folds=0,
               visible_satellites=None, unreadable_checkpoints=0)
    p = folder/'observations.json'
    if p.exists():
        doc = json.loads(p.read_text())
        summary = doc['summary']
        assert summary['session_id'] == row['session_id']
        assert doc['signature']['manifest_sha256'] == meta['manifest_sha256']
        assert summary['sample_rate_hz'] == 2_500_000
        row.update(exported=True, candidates=summary['projected_passing_candidates'],
                   passing_windows=summary['passing_windows'],
                   scheduled_receiver_probes=summary['all_scheduled_probes'],
                   no_retained_iq_events=len(summary['events_without_retained_iq']))
    p=folder/'orbit-bank/receipt.json'
    if p.exists():
        bank=json.loads(p.read_text())
        assert bank['status']=='complete'
        row.update(orbit_ready=True,visible_satellites=bank['retained_count'])
    p = folder/'refinement/refined.json'
    if p.exists():
        r = json.loads(p.read_text())['summary']
        assert r['status'] == 'complete' and r['completed_candidates'] == row['candidates']
        row.update(refined=True,refined_candidates=r['completed_candidates'],failed_refinements=r['failed_refinements'])
    else:
        # Visit files are completed atomic work units; a stopped run may not
        # have written its final progress summary. Do not count pending tasks.
        for p in (folder/'refinement').glob('visit-*.json'):
            try:
                r = json.loads(p.read_text())
            except json.JSONDecodeError:
                row['unreadable_checkpoints'] += 1
                continue  # A currently writing or incomplete checkpoint is not completed work.
            row['refined_candidates'] += len(r['records'])
    folds = list((folder/'seed-timing-v6/calibration-v2').glob('fold-*.json'))
    row['calibration_folds'] = len(folds)
    row['calibrated'] = len(folds) == 5 and all(
        json.loads(p.read_text())['pre_fit_attempts']['fitted-c'][-1]['success'] and
        all(a['success'] for a in json.loads(p.read_text())['arms'].values()) for p in folds)
    row['associated'] = (WORK/'associations'/label/'summary.json').exists()
    p = WORK/'paired'/f'{label}.json'
    if p.exists():
        d = json.loads(p.read_text())
        assert d['scan'] == label and d['reconstruction_max_hz'] < 1e-5
        row['sky_ready'] = True
    return row


def run():
    cohort = json.loads((HERE/'cohort.json').read_text())
    rows = [inspect_scan(s) for s in cohort['scans'] if s['label'] in cohort['new_labels']]
    totals = {k: sum(r[k] for r in rows) for k in ('exported','orbit_ready','refined','calibrated','associated','sky_ready',
              'candidates','passing_windows','scheduled_receiver_probes','refined_candidates')}
    pilot_results=[]
    for row in rows:
        if row['associated']:
            pilot_results.extend(json.loads((WORK/'associations'/row['label']/'summary.json').read_text()))
    result = dict(updated_utc=datetime.now(timezone.utc).isoformat(), original_scans=18,
                  requested_additions=64, target_total_scans=82, totals=totals, scans=rows,
                  status='complete' if totals['sky_ready']==64 else 'partial_processing',
                  scope='New recorded scans only. Passing-window counts are not associated-window counts. IQ export samples three visits; full payload verification happens during refinement.',
                  selected_without_fit_scores=True, processing_basis=cohort['pipeline'], association_results=pilot_results,
                  uncertainty=cohort['spacing_caveat'])
    (HERE/'progress.json').write_text(json.dumps(result,indent=2))
    with (HERE/'scans.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    fig,axs=plt.subplots(2,1,figsize=(16,8),gridspec_kw={'height_ratios':[1,2]})
    for is_new,label,color in [(False,'Original 18','#0072B2'),(True,'Additional 64','#D55E00')]:
        records=[s for s in cohort['scans'] if (s['label'] in cohort['new_labels'])==is_new]
        times=[datetime.fromisoformat(s['capture_utc']) for s in records]
        axs[0].scatter(times,[int(is_new)]*len(times),c=color,s=32,label=label)
    axs[0].set(yticks=[0,1],yticklabels=['Original 18','Additional 64'],ylim=(-.5,1.5),xlabel='Capture time (UTC)')
    axs[0].xaxis.set_major_formatter(mdates.DateFormatter('%b %d\n%H:%M',tz=timezone.utc))
    axs[0].grid(axis='x',alpha=.2)
    axs[1].bar([r['label'] for r in rows],[r['candidates'] for r in rows],color='#dddddd',label='Saved passing candidates')
    axs[1].bar([r['label'] for r in rows],[r['refined_candidates'] for r in rows],color='#009E73',label='Refinement completed (includes failed attempts)')
    axs[1].tick_params(axis='x',labelrotation=90,labelsize=8)
    axs[1].set(ylabel='Candidate records—not independent windows')
    axs[1].legend(fontsize=9);axs[1].grid(axis='y',alpha=.2)
    fig.suptitle(f"Sky-map expansion · {totals['exported']}/64 inputs exported · {totals['sky_ready']}/64 additions sky-ready",fontsize=18)
    fig.text(.5,.025,'All additions: 2.5 MS/s, dual RX, capture-bound LT3D-004B 40° fixture. Selected by time only.\n'
             'The original 18-scan maps remain unchanged. This is processing progress, not an 82-scan sky result.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.08,1,.95));fig.savefig(HERE/'cohort-progress.png',dpi=150);plt.close(fig)
    cols=('label','session_id','capture_utc','candidates','passing_windows','visible_satellites','refined_candidates','calibration_folds','associated','sky_ready')
    table='<table><tr>'+''.join(f'<th>{k}</th>' for k in cols)+'</tr>'+''.join('<tr>'+''.join(f'<td>{html.escape(str(r[k]))}</td>' for k in cols)+'</tr>' for r in rows)+'</table>'
    interim=HERE/f"maps-{18+totals['sky_ready']}-scans"
    maps=(f'<h2>Interim sky maps: {18+totals["sky_ready"]}/82 scans</h2>'
          f'<p><a href="{interim.name}/comparison.png">Original/additional/combined comparison</a> · '
          f'<a href="{interim.name}/sensitivity.png">Matched RF/gate sensitivity</a></p>'
          f'<img src="{interim.name}/sky-maps.png">') if (interim/'sky-maps.png').exists() else ''
    results='<h2>Completed association runs</h2><table><tr><th>Scan</th><th>RF arm</th><th>Assigned / passing windows</th><th>Coverage</th><th>Satellites</th><th>Residual RMS (Hz)</th></tr>'
    for r in pilot_results:
        results+=f"<tr><td>{r['scan']}</td><td>{r['arm']}</td><td>{r['assigned']} / {r['denominator']}</td><td>{100*r['coverage']:.1f}%</td><td>{r['satellites']}</td><td>{r['rms_hz']:.1f}</td></tr>"
    results+='</table><p>This table uses the highest refined-margin candidate per passing GLRT window. Sky evidence subsequently considers all refined alternatives. Neither association coverage nor in-sample residual RMS establishes satellite identity or position accuracy.</p>'
    text=f'''<!doctype html><meta charset="utf-8"><title>64-scan sky extension</title>
<style>body{{font:15px system-ui;max-width:1500px;margin:30px auto;padding:20px;line-height:1.5}}img{{width:100%}}table{{border-collapse:collapse;font-size:11px}}td,th{{border:1px solid #ddd;padding:5px}}</style>
<h1>64 additional recordings: N17–N80</h1><p>Target: 82 scans including A, B and N01–N16. Current status: <b>{result['status']}</b>. Updated {result['updated_utc']}.</p>
<img src="cohort-progress.png"><h2>Processing totals</h2><pre>{html.escape(json.dumps(totals,indent=2))}</pre>{results}{maps}
<h2>Comparison protocol</h2><p>{html.escape(cohort['pipeline'])}</p>
<p>Keep original-only, additional-only, and combined maps separate; identical angular smoothing and matching tolerances. Both fitted-c and c=0 calibration arms. Refitting uses the existing baseline convention rather than silently substituting another model. These are conditional reception maps, not absolute antenna gain or blind satellite identity tests.</p>
<p>{html.escape(cohort['spacing_caveat'])} All eligible outcomes will be used to fit the sky model; temporal bootstrap is uncertainty estimation, not a training/test split.</p>
<p>Capture manifest, roof coordinates, receiver orientation and pose digests were revalidated for all selected scans. Each export checks the saved GLRT input, an archived pre-capture TLE snapshot and three IQ visits. Only completed refinement verifies all candidate-bearing IQ visits. Missing IQ and failed refinements remain explicit; no quality-based replacement of selected scans.</p>
<p>Each bounded batch uses at most two concurrent scan stages (up to two refinement workers per scan), one numerical thread per process, a ten-minute per-stage limit and a 25-minute batch deadline. New subprocesses run at reduced CPU priority. Refinement is checkpointed by visit; completed inputs are reused. Interrupted unsealed association/orbit outputs require explicit review. No live RF capture, QNAP writes, localization searches or production association updates.</p>
<h2>Inventory</h2>{table}<p><a href="scans.csv">CSV</a> · <a href="cohort.json">Frozen cohort</a> · <a href="progress.json">Machine-readable progress</a></p>'''
    (HERE/'report.html').write_text(text)
    print(json.dumps(totals),flush=True)


if __name__=='__main__':
    run()
