"""Final held reporting/terminal seal. No new scoring, IQ or position work."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent;OUT=HERE/'held'
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def main():
    p=read(OUT/'protocol.json');s=read(OUT/'summary.json');jobs=read(HERE/'held_job_receipts.json')
    checks=dict(frozen_hashes=all(sha(path)==h for path,h in p['files'].items()),
        all_12_terminal_jobs=len(jobs['jobs'])==12 and all(j['exit_code']==0 and j['completed_windows']==24 and j['failed_windows']==0 for j in jobs['jobs']),
        all_288_windows=sum(e['paired_windows'] for e in s['execution'])==288,
        all_576_unique_owners=s['observed_cells']==576 and s['unique_native_owners']==576,
        no_failed_windows=not s['failed_windows'],all_checkpoints=s['all_checkpoints'],
        all_selection_receipts=s['all_selection_receipts'],all_native_read_receipts=s['all_native_read_receipts'],
        no_missing_original_exports=s['counts']['original_export_missing']==0,
        no_best_method_or_union=s['methods_never_combined'],no_retune=s['no_target_retune'],
        no_recovered_donors=s['no_recovered_donors'],process_bounds=all(e['seconds']<580 for e in s['execution']),
        preexecution_audit=read(OUT/'execution_audit.json')['all_passed'])
    if not all(checks.values()):raise ValueError('held terminal audit failed: '+str(checks))
    totals={key:sum(e[key] for e in s['execution']) for key in ['seconds','read_verify_seconds','R01_scoring_seconds','R02_scoring_seconds']}
    terminal=dict(schema='held-terminal-execution-audit/v1',completed_utc_ns=time.time_ns(),checks=checks,all_passed=True,
        jobs=jobs['jobs'],timing_totals=totals,maximum_workers=2,BLAS_threads=1,process_bound_seconds=580,
        protocol_sha256=sha(OUT/'protocol.json'),raw_scoring_finished=True,additional_experiments=0,
        no_raw_IQ_export=True,no_positions=True,scope='Frozen-method held acquisition only')
    write(OUT/'terminal_execution.json',terminal)
    write(OUT/'verification.json',dict(checks=checks,all_passed=True,wrapper_tests=2,raw_IQ_reads=0,new_scoring_calls=0,position_ready=False))
    report=f'''# Held acquisition transfer: frozen methods remain complementary

All twelve held recordings complete: 288 paired windows, 576 unique receiver
owners, no failed windows or missing original exports. These recordings were
held out from developing this revision, but appeared in older studies; this is
not unseen-location validation. Methods and gates were fixed before outcomes.

| Separate method | Pilot confirmations | Admissions | New original-absent | CH5–8 admissions | CH5–8 new |
|---|---:|---:|---:|---:|---:|
| R01 matched point | 83 | 77 | 3 | 52 | 3 |
| R01 timing search | 222 | 209 | 23 | 139 | 15 |
| R02 consistent linear | 72 | 67 | 4 | 45 | 4 |
| R02 quadratic / fallback | 161 | 157 | 7 | 105 | 6 |
| R02 descriptive legacy | 67 | 59 | 4 | 38 | 4 |

Pilot confirmation means the margin gate alone. Admission additionally requires
compatibility with the selected earlier CFO width. The original full-window
export has 210 positive owners, including 142 in CH5–8; it has different search
and sample exposure. R01 search retains 186 originals, misses 24 and adds 23.
An additions-only application preserves all 210 originals and reaches 233;
CH5–8 grows from 142 to 157. R02 preserves the baseline separately and adds 7,
reaching 217 overall and 148 in CH5–8. No best-method union, hybrid, replacement
or outcome-selected method is implemented. All 122 no-donor cells remain.

![Held acquisition transfer](held_acquisition_transfer.png)

The timing-search acquisition effect transfers to this held panel. The quadratic
point improves the consistent-linear proposal while recovering fewer original-
absent owners than sparse multimode search. Those claims concern RF acquisition,
not correct satellite identity, precise independent Doppler or position accuracy.
R01 search has 13 pilot confirmations outside the earlier compatibility width;
R02 quadratic has 4. They remain separate alternate-pilot evidence.

Frequency conditioning is explicit. Of 157 quadratic admissions, 150 select the
zero residual FFT bin and only 7 select a nonzero bin, at most 1,331.68 Hz. R01
search has 87 nonzero innovations among 209 admissions, reaching 16,867.90 Hz.
The 443.892045 Hz grid origin depends on the donor forecast. Pilot support near
a forecast is not a calibrated fine-frequency likelihood or an additional
independent donor observation. No new uncertainty weights or independent points
are admitted by this scorer. Coherence, causal association and any matched
c=0/fitted-c position conclusion are owned by the independent integration.

One verified raw read supplies both immutable methods. R01 nomination is sealed
on its search samples before disjoint confirmation and before R02 full-window
controls. R02 receives its frozen points directly. Original target outcomes are
evaluation-only; newly recovered points never feed histories. Current native
index/IQ/generation/receiver authority and full reader exhaustion are checked.
Reused paired detector parity is global unchanged-runtime evidence, not a fresh
blind replay on each held window. No source, forecast or bound artifact changed
during the jobs. All checkpoints, selections and terminal/source audits pass.

The twelve shards take 32.94–65.51 seconds each, totaling {totals['seconds']:.2f}
process-seconds with at most two workers and 580-second/BLAS1 bounds. Separate
timers total {totals['read_verify_seconds']:.2f} seconds for native reading and
verification, {totals['R01_scoring_seconds']:.2f} for R01 and
{totals['R02_scoring_seconds']:.2f} for R02. Full per-case/channel/RX outcomes,
retained/lost originals, additions-only coverage, innovations and failures are
in summary.json and cells.csv. Candidate manifests preserve separate methods
and owners; they do not authorize an automatic position run.

There is no new RF, QNAP write, production edit, git mutation, retuning or extra
experiment. Scoring is finished. This terminal seal freezes source snapshots,
all numerical outcomes, checkpoints and receipts. The lean publication includes
findings, compact tables, candidates, figure and verification; full immutable
outcomes stay local under hashes, with no raw IQ export. The root publishes the
combined acquisition/coherence/position conclusion; this branch stops here.
'''
    with (OUT/'FINDINGS.md').open('x') as f:f.write(report)
    source_dir=OUT/'sources';source_dir.mkdir()
    for name in ['held.py','test_held.py','summarize_held.py','seal_held.py','expansion.py','scorer.py']:
        with (source_dir/name).open('xb') as f:f.write((HERE/name).read_bytes())
    names=['FINDINGS.md','summary.json','cells.csv','r01_search_candidate_manifest.json','r02_quadratic_candidate_manifest.json',
        'protocol.json','run_authorization.json','execution_audit.json','test_results.json','terminal_execution.json','verification.json',
        'held_acquisition_transfer.png','held_acquisition_transfer.pdf']
    names+=['sources/'+p.name for p in sorted(source_dir.iterdir())]
    names+=['publication_allowlist.json','artifact_seal.json','publication_manifest.json']
    write(OUT/'publication_allowlist.json',dict(files=names,raw_IQ_included=False,full_outcomes_checkpoints_selections_local_only=True))
    local=sorted(f for f in OUT.rglob('*') if f.is_file() and f.name not in ['artifact_seal.json','publication_manifest.json'])
    write(OUT/'artifact_seal.json',dict(schema='held-acquisition-terminal-artifact-seal/v1',sealed_utc_ns=time.time_ns(),
        files={str(f.relative_to(OUT)):dict(sha256=sha(f),bytes=f.stat().st_size) for f in local},
        terminal=True,additional_experiments_authorized=False,no_raw_IQ=True,independent_added_Doppler_points=0,no_positions=True))
    files=[OUT/n for n in names if n!='publication_manifest.json']
    write(OUT/'publication_manifest.json',dict(files={str(f.relative_to(OUT)):dict(sha256=sha(f),bytes=f.stat().st_size) for f in files},
        artifact_seal_sha256=sha(OUT/'artifact_seal.json'),raw_IQ_included=False,terminal=True))
    for name in ['artifact_seal.json','publication_manifest.json']:
        for path,entry in read(OUT/name)['files'].items():
            if sha(OUT/path)!=entry['sha256']:raise ValueError('final seal mismatch: '+path)
    print('held terminal seal',sha(OUT/'artifact_seal.json'),'publication manifest',sha(OUT/'publication_manifest.json'),flush=True)


if __name__=='__main__':main()
