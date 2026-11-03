"""Coverage accounting and paginated independent-position/RMS-cut figures."""
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

HERE=Path(__file__).resolve().parent
ASSOC=Path('/srv/bulk/leo/t1-at-v1-replication-20261004')
WORK=Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')
OLD=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
SCANS=['A','B']+[f'N{i:02}' for i in range(1,17)]
ARMS={'fitted-c':'#0077ad','zero-c':'#df6900'}


def historical_audit():
    path=HERE/'historical-position-audit.json'
    return json.loads(path.read_text())['rows'] if path.exists() else []


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def coverage():
    rows=[]
    cohort=json.loads((HERE.parent/'2026_10_04_ds13_18_scan_benchmark/cohort-v2.json').read_text())
    scans={r['label']:r for r in cohort['scans']}
    for scan in SCANS:
        folder=ASSOC/('replayed-ab-verified' if scan in ('A','B') else 'attempt2' if scan in ('N01','N02') else 'remaining')/scan
        for r in json.loads((folder/'summary.json').read_text()):
            if scan.startswith('N'):
                previous=json.loads((OLD/scan/'seed-timing-v6/selection-p10-g600-t1.json').read_text())['arms'][r['arm']]['replacement']['final']
                assert previous['denominator']==r['denominator']
            else:
                previous=r # Verified exact historical replication, not rebuilt-bank comparison.
            metadata=scans[scan]
            rows.append(dict(scan=scan,session_id=metadata['session_id'],sample_rate_hz=metadata['sample_rate_hz'],
                capture_utc=metadata['capture_utc'],arm=r['arm'],assigned=r['assigned'],denominator=r['denominator'],
                coverage=r['coverage'],unassigned=r['unassigned'],satellites=r['satellites'],rms_hz=r['rms_hz'],
                previous_assigned=previous['assigned'],previous_coverage=previous['coverage'],
                delta_pp=100*(r['coverage']-previous['coverage']),accepted_replacements=r['accepted_replacements'],
                comparison='historical exact replay' if scan in ('A','B') else 'previous top-only replacement',
                source=str(folder/f'{r["arm"]}.json')))
    write_csv(HERE/'cohort-coverage.csv',rows)
    fig,axes=plt.subplots(2,1,figsize=(16,8),sharex=True,sharey=True)
    for ax,(arm,color) in zip(axes,ARMS.items()):
        entries=[r for r in rows if r['arm']==arm];x=np.arange(len(entries))
        ax.bar(x-.19,[100*r['previous_coverage'] for r in entries],.38,color='.75',label='Previous top-only')
        bars=ax.bar(x+.19,[100*r['coverage'] for r in entries],.38,color=color,label='T1-AT v1')
        ax.bar_label(bars,labels=[f'{100*r["coverage"]:.1f}' for r in entries],padding=3,fontsize=8)
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0');ax.set_ylim(0,105)
        ax.axhline(90,color='.4',ls=':',lw=1);ax.set_ylabel('Associated passing windows (%)');ax.legend(loc='lower right')
        ax.set_xticks(x,SCANS);ax.tick_params(labelbottom=True);ax.grid(axis='y',alpha=.2)
    fig.suptitle('T1-AT v1 · full-cohort coverage comparison',fontsize=17)
    fig.text(.5,.012,'One highest-refined-margin candidate per window; identical denominators within each scan.\n'
             'A/B replay historical frozen pools exactly. N scans restore absolute timing and top-only discovery together; calibration/refinement remain frozen.\n'
             'Candidate support, not validated satellite identity or position accuracy.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.09,1,.97));fig.savefig(HERE/'cohort-coverage.png',dpi=160);plt.close(fig)
    return rows


def load(scan,case):
    path=WORK/scan/f'{case}.json'
    if not path.exists(): return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        # A live worker may be publishing this file; show pending, never partial values.
        print('Pending publication:',path)
        return None


def panel(ax,scan,ranking,title,cuts=False):
    values=(50,100,300,600) if cuts else (25,50,75,100)
    labels=[str(v) for v in values]; xs=np.arange(4)
    records=[load(scan,f'rms-cut-{v}' if cuts else 'all-100' if v==100 else f'{ranking}-{v}') for v in values]
    audit={(r['case'],r['arm']):r for r in historical_audit() if r['scan']==scan}
    for arm,color in ARMS.items():
        distances=[r['arms'][arm]['distance_m'] if r and arm in r['arms'] else np.nan for r in records]
        ax.plot(xs,distances,color=color,lw=1.5)
        for x,y,r in zip(xs,distances,records):
            if not np.isfinite(y): continue
            a=r['arms'][arm];m='X' if not a['converged'] else '^' if a['boundary'] else '*' if a['ambiguous'] else 'o'
            ax.scatter(x,y,c=color,s=75 if m!='o' else 35,marker=m,edgecolors='black' if m!='o' else color,zorder=3)
            peer=r['arms']['zero-c' if arm=='fitted-c' else 'fitted-c']['distance_m']
            up=y>=peer if y!=peer else arm=='fitted-c'
            known_better=audit.get((r['case_id'],arm),{}).get('historical_better_score',False)
            ax.annotate(f'{y:.0f}'+('†' if known_better else ''),(x,y),xytext=(0,8 if up else -13),textcoords='offset points',ha='center',fontsize=7,color=color)
    for x,r in zip(xs,records):
        if r is None: ax.text(x,1050,'Pending',rotation=90,ha='center',va='center',color='.5',fontsize=8)
        elif not r['arms']: ax.text(x,1050,'No satellites',rotation=90,ha='center',va='center',color='.5',fontsize=8)
    if cuts:
        labels=[label+(f'\n{r["candidates"]}S / {r["windows"]}W' if r else '\npending')
                for label,r in zip(labels,records)]
    roof_case=load(scan,'all-100')
    ranking_warning=(ranking in ('rms','rms-cut') and roof_case is not None
                     and not roof_case['arms']['fitted-c']['roof']['success'])
    ax.set_title(f'{scan}'+('‡' if ranking_warning else '')+f' · {title}',fontsize=10)
    ax.set_xticks(xs,labels);ax.set_ylim(-100,2200)
    ax.set_xlim(-.15,3.15)
    ax.tick_params(axis='x',labelsize=8)
    ax.axhline(2000,c='.5',ls=':',lw=1);ax.grid(alpha=.2)
    ax.set_xlabel('Satellite RMS ceiling (Hz)' if cuts else 'Top fraction retained (%)')
    ax.set_ylabel('Best-found distance from roof (m)')


def figures():
    handles=[Line2D([],[],color=c,marker='o',label='Fitted c' if a=='fitted-c' else 'c = 0') for a,c in ARMS.items()]
    handles += [Line2D([],[],color='black',ls='',marker=m,label=t) for m,t in [('^','2 km boundary'),('*','Ambiguous'),('X','Unconverged')]]
    for page,start in enumerate(range(0,len(SCANS),3),1):
        scans=SCANS[start:start+3]
        fig,axes=plt.subplots(3,3,figsize=(16,12))
        for i,scan in enumerate(scans):
            for j,(ranking,title) in enumerate([('rms','Lowest satellite RMS'),('support','Most windows per satellite'),('glrt','Highest window GLRT score')]):
                panel(axes[i,j],scan,ranking,title)
        fig.suptitle('T1-AT · association subsets: independent 2 km position searches',fontsize=17,y=.992)
        fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.974),ncol=5,frameon=False)
        fig.text(.5,.015,'Identical memberships, satellite banks, priors and search budgets in both RF arms. Each scan fitted independently.\n'
            'Rankings frozen at fitted-c roof profile. 100% = associated top-response windows. Historical RX baseline fixed; extra RX lines, c and timing refitted.\n'
            'Three starts plus checks. † = better archived same-input score; ‡ = unconverged roof used for RMS ranking. Not globally certified.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.08,1,.945));fig.savefig(HERE/f'cohort-subsets-{page:02}.png',dpi=150);plt.close(fig)
    for page,start in enumerate(range(0,len(SCANS),6),1):
        fig,axes=plt.subplots(3,2,figsize=(13,12))
        for ax,scan in zip(axes.flat,SCANS[start:start+6]): panel(ax,scan,'rms-cut','Cumulative RMS filter',True)
        fig.suptitle('T1-AT · satellite RMS thresholds: independent 2 km position searches',fontsize=16,y=.992)
        fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.974),ncol=5,frameon=False)
        fig.text(.5,.015,'Keep satellites with fitted-c roof RMS ≤50 / ≤100 / ≤300 / ≤600 Hz, using their assigned top-response windows.\n'
            'Cuts frozen before searching; identical subsets in both RF arms. Association gate remains 600 Hz.\n'
            'S = satellites / W = windows. ‡ = unconverged roof used for RMS cuts. Best found, not global certification or blind validation.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.08,1,.945));fig.savefig(HERE/f'cohort-rms-thresholds-{page:02}.png',dpi=150);plt.close(fig)


def rms_strata():
    labels=['≤50 Hz','50–100 Hz','100–300 Hz','300–600 Hz','>600 Hz']
    colors=['#00796b','#68a9a0','#edc45a','#ed913b','#b23a48']
    rows=[];satellites=[];windows=[];names=[]
    for scan in SCANS:
        full=load(scan,'all-100')
        with np.load(WORK/scan/'input.npz') as z: owners=z['owners']
        roof_ok=full['arms']['fitted-c']['roof']['success']
        names.append(scan+('‡' if not roof_ok else ''))
        sc=np.zeros(5,int);wc=np.zeros(5,int)
        for number,rms in full['roof_owner_rms_hz'].items():
            bucket=int(np.searchsorted([50,100,300,600],rms,side='left'))
            count=int(np.sum(owners==int(number)))
            sc[bucket]+=1;wc[bucket]+=count
            rows.append(dict(scan=scan,satellite=int(number),roof_owner_rms_hz=rms,
                             assigned_windows=count,stratum=labels[bucket],roof_converged=roof_ok))
        assert sc.sum()==full['candidates'] and wc.sum()==full['windows']
        satellites.append(sc);windows.append(wc)
    write_csv(HERE/'cohort-rms-strata.csv',rows)
    fig,axes=plt.subplots(2,1,figsize=(16,8),sharex=True,sharey=True)
    for ax,counts,title in zip(axes,(satellites,windows),('Satellite distribution','Assigned-window distribution')):
        counts=np.asarray(counts);fractions=100*counts/counts.sum(axis=1,keepdims=True)
        bottom=np.zeros(len(SCANS));x=np.arange(len(SCANS))
        for i,(label,color) in enumerate(zip(labels,colors)):
            ax.bar(x,fractions[:,i],bottom=bottom,color=color,label=label)
            bottom+=fractions[:,i]
        for i,total in enumerate(counts.sum(axis=1)): ax.text(i,102,str(total),ha='center',fontsize=8)
        ax.set_ylim(0,112);ax.set_ylabel('Share (%)');ax.set_title(title+' · totals above bars')
        ax.set_xticks(x,names);ax.tick_params(labelbottom=True);ax.grid(axis='y',alpha=.15)
    fig.suptitle('T1-AT · disjoint residual strata at the known roof',fontsize=17)
    fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.952),ncol=5,frameon=False)
    fig.text(.5,.018,'RMS uses each satellite’s original T1-AT members after the full fitted-c roof profile. These are disjoint bins, not new searches.\n'
        'Position-filter curves use cumulative ceilings. ‡ = roof fit not converged; those RMS strata/rankings are provisional.\n'
        'The soft position likelihood can favor a different bank satellite; owner RMS can therefore exceed the original 600 Hz association gate.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.11,1,.92));fig.savefig(HERE/'cohort-rms-strata.png',dpi=160);plt.close(fig)


def position_table():
    rows=[]
    for scan in SCANS:
        for path in sorted((WORK/scan).glob('*.json')):
            if path.name=='input.json' or path.name.endswith('-partial.json'): continue
            r=load(scan,path.stem)
            if r is None: continue
            for arm in ARMS:
                a=r['arms'].get(arm)
                rows.append(dict(scan=scan,case=r['case_id'],arm=arm,
                    state='complete' if a else 'empty-subset',windows=r['windows'],satellites=r['candidates'],
                    distance_m=a['distance_m'] if a else None,
                    east_m=1000*a['best']['point_km'][0] if a else None,
                    north_m=1000*a['best']['point_km'][1] if a else None,
                    roof_score=a['roof']['objective'] if a else None,
                    roof_converged=a['roof']['success'] if a else None,
                    roof_kkt_residual=a['roof']['kkt_residual'] if a else None,
                    best_score=a['best']['objective'] if a else None,
                    delta_score=a['delta_score'] if a else None,
                    boundary=a['boundary'] if a else None,converged=a['converged'] if a else None,
                    ambiguous=a['ambiguous'] if a else None,
                    kkt_residual=a['best']['kkt_residual'] if a else None,source=str(path),
                    source_sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()))
    if rows: write_csv(HERE/'cohort-positions.csv',rows)
    return rows


def report(rows,positions):
    cases={(r['scan'],r['case']) for r in positions}
    rendered_at=datetime.now(timezone.utc).isoformat(timespec='seconds')
    tables=[]
    for scan in SCANS:
        arms={r['arm']:r for r in rows if r['scan']==scan}
        cells=[scan,arms['fitted-c']['denominator']]
        for arm in ARMS:
            r=arms[arm]
            cells += [f"{r['assigned']} ({100*r['coverage']:.2f}%)",f"{r['delta_pp']:+.2f}",
                      r['satellites'],f"{r['rms_hz']:.1f}"]
        tables.append('<tr>'+''.join(f'<td>{html.escape(str(c))}</td>' for c in cells)+'</tr>')
    figures_html=''.join(f'<h3>Subset comparison {i}</h3><img src="cohort-subsets-{i:02}.png">' for i in range(1,7))
    figures_html+=''.join(f'<h3>RMS thresholds {i}</h3><img src="cohort-rms-thresholds-{i:02}.png">' for i in range(1,4))
    historical=historical_audit()
    better=sum(r.get('historical_better_score',False) for r in historical)
    comparable=sum(r['same_rows'] and r['same_bank'] for r in historical)
    provisional=[scan for scan in SCANS if not load(scan,'all-100')['arms']['fitted-c']['roof']['success']]
    numerical=f'''<h3>Search reproducibility audit</h3><p>The archived A/B chart is not overwritten.
For {comparable} comparable case/arm pairs, evaluating the archived vectors on the new objective reproduces
their stored scores to within 10<sup>−7</sup>. In {better} pairs the archived solution has a lower score than
this bounded rerun (marked †). These are different local basins, not changed scoring or coverage.
For B at 100%, the fitted-c score is 43,261.36 here versus the archived 43,250.92;
the distances are about 1,142 m and 1,129 m respectively. A lower score is not necessarily a lower position error.</p>
<p>B's three RMS-ranked subsets also differ from the archive because the new roof fit changes the RMS ranking.
Those six RF-arm cases are not treated as identical-input optimizer comparisons. The assignment coverage itself is unchanged.</p>
<p><a href="historical-position-audit.json">Direct cross-evaluation audit</a> ·
<a href="subset-position-AB-N01-N02.png">Earlier A/B reference with N01/N02 additions</a> ·
<a href="cohort-positions.csv">All completed position/filter cases (CSV)</a></p>'''
    runtime='''<h2>Adaptive analysis integration</h2>
<p>The optional <code>--t1-at-discovery-input</code> stage accepts qualified orbit-blind refinement,
frozen receiver/RF calibration and a full near-visible orbit bank. Runtime code selects the top response,
discovers absolute ±20 s timing hypotheses across that bank, then runs greedy + replacement with both RF arms.
It does not depend on archived report scripts. The alternative <code>--t1-at-input</code> accepts an already
prepared matched timing-mode pool. Neither option silently creates calibration or recollects RF data.</p>
<p>Outputs bind capture, analysis and prepared-input digests, use an immutable T1-AT namespace, and cache
exact inputs. Timeouts are partial, never published as completed solutions. The input probe stride follows
the requested analysis product. Existing default analysis is unchanged unless a T1-AT input is supplied.</p>
<p>Numerical verification: selection exactly matches both archived RF arms for all 18 scans (36 comparisons).
Fresh full-bank runtime discovery reproduces all 16 N scans in both RF arms: exact assigned-window sets and
satellite IDs, with residual agreement within 10<sup>−6</sup> Hz. Sampled calibrated predictions and timing derivatives
agree to 10<sup>−7</sup> Hz tolerance (maximum frequency discrepancy 6 × 10<sup>−11</sup> Hz).
The standard adaptive CLI was exercised on the existing N01 capture/analysis.
Integration is committed locally as <code>2fcacc87d</code> on <code>codex/t1-at-adaptive-analysis</code>;
78 component/regression tests pass, plus six research-runner tests. It is not deployed or pushed.</p>
<p><a href="production-core-parity.json">36-arm selection parity</a> ·
<a href="discovery-pipeline-results.json">32-arm runtime full-bank verification</a> ·
<a href="cohort-audit.json">Current score/membership audit</a></p>
<h3>Opt-in invocation</h3>
<pre>python -m leo.cli.adaptive_hop_analysis \\
  --bulk-root /srv/bulk/leo \\
  --session-id scan-fw-0c4c127b1f80a01b \\
  --probe-stride-ms 120 --metrics-only \\
  --t1-at-discovery-input /srv/bulk/leo/t1-at-v1-replication-20261004/discovery-pipeline/N01/input.json \\
  --t1-at-maximum-seconds 600</pre>
<p>Use the integration branch environment. Inputs must bind the same capture and analysis manifests; the
example uses the already-qualified N01 evidence, not a template to relabel as another scan. The runtime needs
no report-module imports. The report's export bridge documents how these archived research inputs were converted
to the public contract. T1-AT is an explicit opt-in stage, not an automatic calibration/refinement replacement.</p>'''
    (HERE/'cohort-results.html').write_text('''<!doctype html><meta charset="utf-8"><title>T1-AT cohort results</title>
<style>body{font:16px system-ui;max-width:1500px;margin:40px auto;padding:0 20px;color:#19212a}img{width:100%}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:right}th:first-child,td:first-child{text-align:left}.status{background:#edf4fa;padding:18px}a{color:#0077ad}</style>
<h1>T1-AT v1: A, B and N01–N16</h1>
<p class="status">All 18 association reruns complete. Position/filter cases completed: '''+str(len(cases))+''' / 252.
Each nonempty case has matched fitted-c and c=0 arms. Empty subsets are explicit, not zero-error solutions.
Snapshot: '''+rendered_at+'''.</p>
<h2>Coverage is not position accuracy</h2>
<p>One highest-refined-margin candidate per passing 20 ms receiver/channel window. A/B replay the historical frozen pools exactly.
N scans reuse orbit-blind refinement and qualified saved calibration, restoring absolute satellite timing and top-only discovery together.
This is not an isolated timing-only causal ablation, a new IQ refinement run, or held-out identity validation.</p>
<p>A is the original 10 MS/s reference; B and N01–N16 are 2.5 MS/s. Full scan IDs, capture times and rates are
included in the coverage CSV. The added scans use the recorded 40° fixture separation.</p>
<img src="cohort-coverage.png"><p><a href="cohort-coverage.csv">Complete coverage table (CSV)</a></p>
<table><thead><tr><th>Scan</th><th>Windows</th><th>Fitted c assigned</th><th>Δ pp</th><th>Sats</th><th>RMS Hz</th><th>c=0 assigned</th><th>Δ pp</th><th>Sats</th><th>RMS Hz</th></tr></thead><tbody>'''+''.join(tables)+'''</tbody></table>
<h2>Independent position searches</h2>
<p>The known roof supplies the reference and frozen rankings. Fitted-c assignments select the included windows and candidate bank in both RF arms;
the discrete T1-AT selector is not rerun during position searches. The finite-set likelihood still marginalizes over the fixed satellite bank,
so its soft association probabilities can change. It is not a fixed-owner least-squares objective.
The frozen receiver baseline is shared, while extra receiver lines, the RF coefficient and timing are refitted.
Three starts and identical bounded search budgets in each arm; best-found positions are not globally certified minima.
Triangles denote the 2 km boundary, stars search ambiguity, and X unconverged results. Pending cases are labeled.</p>
<p>RMS filters are cumulative satellite-level cuts at ≤50, ≤100, ≤300 and ≤600 Hz, using the full fitted-c roof profile.
These do not change the 600 Hz association gate or the GLRT activity threshold. All RMS and position comparisons here are in-sample diagnostics.</p>
<p>Roof profiles used for RMS ranking/cuts remain unconverged for '''+', '.join(provisional)+'''. Those scans are marked ‡;
their RMS-derived selections are provisional, even if a subsequent position search converges. The saved results are retained, not silently repaired.</p>
<h3>Disjoint RMS strata</h3><img src="cohort-rms-strata.png"><p><a href="cohort-rms-strata.csv">Per-satellite strata and window counts</a></p>
'''+numerical+figures_html+runtime)


if __name__=='__main__':
    rows=coverage();positions=position_table();figures();rms_strata();report(rows,positions)
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm and r['scan'].startswith('N')]
        total=sum(r['denominator'] for r in selected)
        print(arm,'N weighted coverage',sum(r['assigned'] for r in selected)/total,
              'previous',sum(r['previous_assigned'] for r in selected)/total,
              'improved scans',sum(r['delta_pp']>0 for r in selected),'of',len(selected))
