"""Standalone report from saved factorial results; no fitting or collection."""
from collections import defaultdict
from datetime import datetime
import json
from statistics import median
from zoneinfo import ZoneInfo

import factorial as study


def table(headers, rows):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(map(cell, headers)) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *['| ' + ' | '.join(map(cell, row)) + ' |' for row in rows]])


def evidence_summary(rows, pairs):
    completed = [r for r in rows if r['status'] == 'complete']
    grouped = defaultdict(list)
    for row in completed:
        grouped[row['scan']].append(row)
    contrasts = defaultdict(list)
    for pair in pairs:
        contrasts[(pair['contrast'], pair['held_fixed'])].append(pair)
    effects = []
    for (contrast, fixed), group in sorted(contrasts.items()):
        qualified = [p for p in group if p['both_converged'] and not p['either_boundary']]
        effects.append(dict(contrast=contrast, held_fixed=fixed, available=len(group),
            qualified=len(qualified), scans=[p['scan'] for p in qualified],
            median_change_m=median(p['change_m'] for p in qualified) if qualified else None,
            improved=sum(p['change_m'] < 0 for p in qualified)))
    return dict(planned=len(rows), saved=len(completed),
        converged=sum(bool(r['converged']) for r in completed),
        boundary=sum(bool(r['boundary']) for r in completed),
        complete_scans=sorted(s for s, group in grouped.items() if len(group) == 16),
        effects=effects)


def write_report(rows, pairs, timestamp):
    summary = evidence_summary(rows, pairs)
    complete = [r for r in rows if r['status'] == 'complete']
    cohort = json.loads(study.stage.COHORT.read_text())
    local = datetime.fromisoformat(timestamp).astimezone(ZoneInfo('America/Los_Angeles'))
    status = 'Draft with incomplete evaluation' if summary['saved'] < summary['planned'] else 'Evaluation results'
    sections = ['# Recent scan localization comparison',
        f'{status}. Snapshot: {local:%Y-%m-%d %H:%M %Z}.',
        'This study compares orbit-blind GLRT refinement, receiver cone priors, and '
        'T1-AT versus V16 position scoring on 16 recent scans, with a matched fitted-c '
        'versus c = 0 control. The central endpoint is position error, not merely signal coverage.',
        f"**{summary['saved']} of {summary['planned']} position fits are saved; "
        f"{summary['converged']} pass convergence checks and {summary['boundary']} hit the search boundary.** "
        f"All 16 cases are saved for {len(summary['complete_scans'])} of 16 scans. "
        'A saved but unconverged fit remains provisional. Missing fits are not zero-error results.',
        '## Current findings',
        ('The cohort evaluation is incomplete. Paired results below describe only the available '
         'scans; they cannot yet establish a cohort-wide winner.' if summary['saved'] < summary['planned'] else
         'All configured cases have saved results. Interpret comparisons alongside convergence and boundary flags; '
         'saved results alone do not certify global minima.'),
        'The table reports one contrast at a time with all other switches held fixed. '
        'Only pairs with two converged interior solutions enter the median change. '
        'Negative change means lower position error. Each row has at most one pair per scan.',
        table(['Change', 'Held fixed', 'Available pairs', 'Converged interior pairs',
               'Median error change (m)', 'Improved pairs'],
              [[e['contrast'], e['held_fixed'], e['available'], e['qualified'],
                '—' if e['median_change_m'] is None else f"{e['median_change_m']:+.1f}",
                f"{e['improved']}/{e['qualified']}"] for e in summary['effects']]),
        '## Position errors for every planned case',
        'Gray cells are pending. A cross marks an unconverged saved fit; a triangle marks the 4 km boundary. '
        'Both RF arms use identical branch inputs and maximum search budgets.',
        '![Position errors for all scans and configurations](position-error-matrix.png)',
        '## Paired effects on position error',
        'Each point compares the same scan under one changed switch. Points below the diagonal '
        'have lower position error after the switch. The figure uses the displayed fixed settings; '
        'the paired table and CSV cover all settings. Sample-rate colors describe different captures, '
        'not randomized sample-rate treatments. Crosses and triangles remain provisional or constrained.',
        '![Matched changes from refinement, score model, and cone prior](paired-position-effects.png)',
        '## Per scan comparisons',
        '![Available individual scan comparisons](available-scan-comparison.png)',
        '## Coverage and frequency fit',
        'The following rows use cone-off fitted-c fits to avoid repeating branch coverage eight times. '
        'Coverage is fixed before final position fitting; changing the score model can change RMS and position '
        'without changing this coverage. RMS is posterior weighted over the frozen associated observations. '
        'Strong final support counts windows whose largest satellite responsibility exceeds 0.5, divided '
        'by the assigned windows used for fitting. It is model-dependent support, not independently validated identity.',
        table(['Scan', 'Measurements', 'Model', 'Satellites', 'Assigned / passing windows', 'Coverage',
               'Strong final support / assigned', 'RMS (Hz)', 'Position error (m)', 'Converged'],
              [[r['scan'], r['refinement'], r['model'], r['selected_satellites'],
                f"{r['assigned_windows']} / {r['passing_windows']}", f"{100*r['coverage']:.1f}%",
                f"{r['strong_soft_windows']} / {r['assigned_windows']}",
                f"{r['posterior_rms_hz']:.1f}", f"{r['distance_m']:.1f}", r['converged']]
               for r in complete if r['cone']=='off' and r['arm']=='fitted-c']),
        '## Frozen cohort',
        'Capture times below are Pacific time. Sample rates are native recorded rates. The fixed selection '
        'window was October 5, 2026, 10:26:39–18:26:39 PDT. No scan is substituted because its result is poor.',
        table(['Short name', 'Scan ID', 'Rate (MS/s)', 'Capture start (PDT)', 'Saved / planned fits'],
              [[s['label'], s['session_id'], s['sample_rate_hz']/1e6,
                datetime.fromisoformat(s['capture_utc']).astimezone(ZoneInfo('America/Los_Angeles')).strftime('%m-%d %H:%M:%S'),
                f"{sum(r['scan']==s['label'] for r in complete)} / 16"] for s in cohort['scans']]),
        (study.stage.HERE/'report_methods.md').read_text(),
        '## Downloads',
        '[All cases CSV](results.csv) · [Paired changes CSV](paired-changes.csv) · '
        '[Frozen protocol](protocol.json) · [Report evidence summary](report-evidence.json) · '
        '[Markdown report](report.md)']
    if (study.REPORT/'continuation-v1/report.md').exists():
        sections.extend(['## Optimizer continuation experiment',
            '[Separate continuation report](continuation-v1/report.md) tests whether '
            'additional optimization resolves provisional fits without changing data or the model. '
            'Its results do not overwrite the fixed-budget figures above. Lower loss and lower '
            'position error are evaluated separately.'])
    if (study.REPORT/'continuation-v1/continuation-effects.png').exists():
        sections.append('![Position and objective changes after optimizer continuation]'
            '(continuation-v1/continuation-effects.png)')
    if (study.REPORT/'continuation-v1/scorecard.md').exists():
        sections.append('[Continuation scorecard](continuation-v1/scorecard.md) compares '
            'identical complete scan cohorts while retaining boundary and unconverged results.')
    if (study.REPORT/'continuation-v1/responsibility-audit.md').exists():
        sections.append('[Responsibility audit](continuation-v1/responsibility-audit.md) '
            'separates satellite-to-satellite changes from transitions to or from clutter '
            'at the original and continued solutions.')
    if (study.REPORT/'optimizer-scaling-v1/report.md').exists():
        sections.append('[Equal-budget optimizer scaling pilot](optimizer-scaling-v1/report.md) '
            'compares ordinary and per-window-scaled SLSQP, with unscaled convergence checks. '
            '[Local gradient checks](../gradient-check.md) document the sampled derivative audit '
            'at the difficult R100-02 continuation point.')
    if (study.stage.HERE/'optimizer-assessment.md').exists():
        sections.append('[Optimizer assessment](../optimizer-assessment.md) summarizes '
            'the continuation, scaling, and matched-polish findings without replacing baseline results.')
    markdown = '\n\n'.join(sections) + '\n'
    (study.REPORT/'report.md').write_text(markdown)
    (study.REPORT/'report-evidence.json').write_text(json.dumps(dict(updated_utc=timestamp, **summary), indent=2))
    from markdown_it import MarkdownIt
    rendered = MarkdownIt('commonmark').enable('table').render(markdown)
    document = '<!doctype html><meta charset="utf-8"><title>Recent scan localization comparison</title>'
    document += '<style>body{font:16px/1.55 system-ui;max-width:1300px;margin:2em auto;padding:0 1.5em}'
    document += 'img{max-width:100%}table{border-collapse:collapse;font-size:14px;display:block;overflow-x:auto}'
    document += 'td,th{padding:.4em .65em;border:1px solid #ddd;text-align:left}code{white-space:pre-wrap}'
    document += 'h2{margin-top:2em}a{color:#006fa8}</style>' + rendered
    (study.REPORT/'report.html').write_text(document)
    return summary
