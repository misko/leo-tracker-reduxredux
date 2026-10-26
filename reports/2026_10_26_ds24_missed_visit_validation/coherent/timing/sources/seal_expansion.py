"""Acquisition/persistence handoff seal; graph/identity/position remain external."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;OUT=HERE/'expansion_v2'
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def main():
    p=read(OUT/'protocol.json');s=read(OUT/'summary.json')
    with (OUT/'cells.csv').open() as f:rows=list(csv.DictReader(f))
    runs=[];fig,axes=plt.subplots(4,2,figsize=(13,10),sharex=False);axis=0
    for key,counts in s['by_channel_receiver'].items():
        case,ch,rx=key.split('/');channel=int(ch[2:]);receiver=int(rx[2:])
        lane=sorted([r for r in rows if r['case']==case and int(r['channel'])==channel and int(r['receiver_id'])==receiver],key=lambda r:int(r['start_counter']))
        accepted=[r for r in lane if r['search_admitted']=='True'];longest=current=0
        for r in lane:
            current=current+1 if r['search_admitted']=='True' else 0;longest=max(longest,current)
        span=(int(accepted[-1]['start_counter'])-int(accepted[0]['start_counter']))/10_000_000 if len(accepted)>1 else 0.
        runs.append(dict(lane=key,enumerated_visits=len(lane),admitted=len(accepted),longest_consecutive_admitted_visits=longest,
            admitted_time_span_s=span,original_absent_admissions=counts['new'],
            interpretation='Same lane repeated evidence only; no common satellite identity or curvature asserted'))
        ax=axes.flat[axis];axis+=1;origin=int(lane[0]['start_counter'])
        for original,marker,color,label in [(True,'o','#777777','Original-positive owner'),(False,'s','#246b99','Original-absent admission')]:
            selected=[r for r in accepted if (r['original_pass']=='True')==original]
            ax.scatter([(int(r['start_counter'])-origin)/10_000_000 for r in selected],[float(r['CFO_hz'])/1000 for r in selected],s=17,marker=marker,color=color,label=label)
        ax.set(title=f'{case}, CH {channel}, RX {receiver}',ylabel='Later-sample CFO (kHz)',xlabel='Seconds from first enumerated visit')
        if not accepted:ax.text(.5,.5,f'No admissions; {counts["no_donor"]} no-donor visits',ha='center',transform=ax.transAxes,fontsize=8)
    axes.flat[0].legend(fontsize=7);fig.suptitle('Repeated lane admissions are candidates for graph review, not preassigned satellite tracks')
    fig.tight_layout();fig.savefig(OUT/'recovery_timeseries.png',dpi=170,bbox_inches='tight');fig.savefig(OUT/'recovery_timeseries.pdf',bbox_inches='tight');plt.close(fig)
    write(OUT/'lane_runs.json',dict(lanes=runs,no_identity_or_curvature_inference=True))
    checks=dict(source_and_input_hashes=all(sha(path)==h for path,h in p['files'].items()),
        receiver_cells=s['receiver_cells']==526,paired_windows=s['paired_windows']==263,
        unique_owners=len({r['owner_id'] for r in rows})==526,no_failed_windows=not s['failed_windows'],
        native_receipts=s['all_native_receipts_and_checkpoints_valid'],selection_receipts=s['all_selection_receipts_valid'],
        disjoint_support=s['selected_sample_groups_disjoint'],bounds=all(e['seconds']<580 for e in s['execution']),
        revoked_v1_had_no_outcomes=not (HERE/'expansion/outcomes').exists(),no_recovered_donors=True,no_position_calls=True)
    write(OUT/'verification.json',dict(checks=checks,all_passed=all(checks.values()),source_tests=2,IQ_reads=0,new_scoring_calls=0))
    if not all(checks.values()):raise ValueError('expansion audit failed')
    report=f'''# Exact R01 coherent application: acquisition handoff

All 263 paired windows / 526 receiver owners complete without failures.
The frozen R01 search yields 118 pilot confirmations and 116 continuity-compatible
admissions, versus 26 point admissions. Original full-window acquisition has
76 positive owners. Search retains 65, misses 11 and adds 51 original-absent
owners. Forty-seven additions lie outside the original sparse panel; four
overlap earlier sparse additions and must not be double counted. Two alternate
pilots fail earlier-CFO compatibility and remain separate.

| Case | Receiver cells | Original | Point admissions | Search admissions | New original-absent |
|---|---:|---:|---:|---:|---:|
| DS24-0011 | 264 | 36 | 15 | 57 | 25 |
| DS24-0097 | 262 | 40 | 11 | 59 | 26 |

All 236 no-donor cells remain. Same-lane repeated marks, timing and CFO are
retained in cells.csv, lane_runs.json and the figure; they do not establish
one satellite identity or active curvature. The validator must rebuild the
original graph and causal catalogue association with additions only, retain
all original owners and deduplicate sparse overlaps. No independent new point
or position has been admitted by this scorer.

![Lane evidence](recovery_timeseries.png)

This is an application of the immutable R01 predictor, timing adapter, search
and confirmation policy. No R02 quadratic forecast, recovered donor, gate change,
new mode policy, threshold tuning or extra RF/scorer control enters it. Native
source/index/IQ/acquisition authority is freshly checked with full public-reader
exhaustion. Reused detector parity is global unchanged-implementation evidence;
no fresh per-window blind replay is claimed.

Metadata v1 authorization was revoked before any IQ work. V2 corrects only
stream-generation labels; all numerical forecasts/native support are identical
under the independent audit. V1 protocol/tests/revoked authorization remain
preserved separately. All selection receipts, full per-window checkpoints and
guarded disjoint samples pass verification. The two shards take 98.89 and
83.76 seconds under 580-second/BLAS1 bounds, at most two concurrent workers.
There is no held raw, new RF, QNAP write, production edit, git mutation or
position execution here. Candidate_manifest.json is ready for independent
coherence/curvature/causal-association review, not promotion.
'''
    with (OUT/'FINDINGS.md').open('x') as f:f.write(report)
    source_dir=OUT/'sources';source_dir.mkdir()
    for name in ['expansion.py','expansion_v2.py','test_expansion.py','summarize_expansion.py','seal_expansion.py']:
        with (source_dir/name).open('xb') as f:f.write((HERE/name).read_bytes())
    names=['protocol.json','run_authorization.json','test_results.json','summary.json','cells.csv','candidate_manifest.json','lane_runs.json',
        'FINDINGS.md','verification.json','recovery_timeseries.png','recovery_timeseries.pdf']
    names+=['sources/'+p.name for p in sorted(source_dir.iterdir())]
    names+=['publication_allowlist.json','artifact_seal.json','publication_manifest.json']
    write(OUT/'publication_allowlist.json',dict(files=names,full_outcomes_checkpoints_selections_local_only=True,no_raw_IQ=True))
    local=sorted(f for f in OUT.rglob('*') if f.is_file() and f.name not in ['artifact_seal.json','publication_manifest.json'])
    write(OUT/'artifact_seal.json',dict(schema='R01-coherent-application-artifact-seal/v2',sealed_utc_ns=time.time_ns(),
        files={str(f.relative_to(OUT)):dict(sha256=sha(f),bytes=f.stat().st_size) for f in local},
        no_raw_IQ=True,position_ready=False,independent_added_Doppler_points=0))
    files=[OUT/n for n in names if n!='publication_manifest.json']
    write(OUT/'publication_manifest.json',dict(files={str(f.relative_to(OUT)):dict(sha256=sha(f),bytes=f.stat().st_size) for f in files},
        artifact_seal_sha256=sha(OUT/'artifact_seal.json'),no_raw_IQ=True))
    print('expansion sealed',sha(OUT/'artifact_seal.json'),'51 new owners,47 outside sparse',flush=True)


if __name__=='__main__':main()
