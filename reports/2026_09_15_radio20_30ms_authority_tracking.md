# Coarse-authority 30-MS/s tracking qualification

**Date:** 15 September 2026  
**Radio:** `1040005e0b100007100010000bf33a5d4d` (`192.168.1.20`)  
**Image:** `glrt-iq-tracking-r30000000-v1`  
**Result:** the first complete 10-second, 751-measurement physical 30-MS/s FPGA tracking run passes

## Result

Retained 2.5-MS/s ARM observations can now extend the causal scheduling
horizon of existing 30-MS/s FPGA pilot jobs. The implementation preserves a
separate native-result history, retains every authority update before use, and
does not rewrite work already submitted to the FPGA. Synthetic positive and
negative controls pass; the final change passes 368 focused controller,
journal, visit, operator and live-authority tests.

The final activity-triggered v13 run completed all **751** stride-ten FPGA
measurements from frame 1,290 through frame 8,790. That is exactly **10.000
seconds** of scheduled source time; the retained FPGA head starts span
10.000038 seconds. The unchanged native diagnostic accepted 466 results and
rejected 285, while 699 retained coarse-authority refreshes kept future work
scheduled. The controller completed and drained normally with zero capture,
CDC and pacer drops. The independent epoch/ownership and journal reviewers
pass all 751 heads, 64 paired-IQ records, and the final clear.

Before the sparse work, four physical runs exercised the dense path. Two acquired the signal and produced
five FPGA episodes. The strongest episode contains **1,158 consecutive FPGA
results, or 1.544 seconds at the 750-Hz pilot cadence**. Its concurrent ARM
observer supports 124 of 130 measurements, while 416 of 1,158 wider native
diagnostics pass their unchanged gate. Those runs established the dense-path
limit and motivated the sustainable stride-ten cadence used by v13.

The dense 750-result/s experiments also established that ARM/sysfs retention
drains about 96.5 results/s. A dense controller therefore falls behind the
750-Hz source clock even when its wall deadline is extended. Firmware commit
`fc77d57dc` adds an opt-in cadence that measures one pilot every ten 750-Hz
frames. Each pilot still enters the FPGA at **30 MS/s** and contains 39,600
native samples; the scheduled measurement rate is **75/s**. The 751st result is
exactly 10.000 seconds after the first result in source time. The existing dense
profiles and their persisted GLT1 bodies are unchanged.

Eight physical sparse-cadence dwells covered all four reviewed upper LOs. They
produced ten handoffs and 1,040 scheduled measurements. The longest operational
episode contained 428 measurements spanning **5.693 seconds**. Independent
review exposed that the first five dwells sometimes retained a newer coarse
authority when it was 33 frames behind the next descriptor frontier, outside
the predictor's 32-frame bound. No descriptor used that stale record, but those
journals correctly fail evidence review. Commit `627654e9c` now refuses such a
refresh until the next observer update. The corrected CH4 validation produced
two independently reviewable clean-loss episodes spanning **1.640 s** and
**0.987 s**. None of those earlier sparse dwells reached 751 measurements.

The later radio-local activity campaign ran ten admitted cycles after one
lease refusal. Three cycles triggered refinement. The final corrected cycle
proved the complete scan-to-follow-up-to-reacquisition path at 1.9403125 GHz:
224 acquisition attempts produced four native episodes and three clean
reacquisitions. The episodes contained 17, 25, 16 and 16 FPGA results; 50 of 74
native diagnostics passed the unchanged gate, and the longest episode spanned
**0.320 s**. Independent epoch/ownership review passes, all FPGA fault and drop
counters are zero, and the exact radio state was restored. That result exposed
the cadence-alias authority issue fixed before v13.

![Radio-local activity triggers and follow-up episode lengths](2026_09_15_radio20_30ms_authority_tracking/activity_followup_outcomes.png)

![Sparse-cadence episode lengths and four-frequency visits](2026_09_15_radio20_30ms_authority_tracking/sparse_tracking_outcomes.png)

![Scheduled episode lengths and handoff times](2026_09_15_radio20_30ms_authority_tracking/tracking_outcomes.png)

## Rates and limits

| Component | Rate | Bound or role |
| --- | ---: | --- |
| FPGA receive and scheduled-pilot input | 30 MS/s | 39,600 native samples per 1.32-ms pilot |
| FPGA scheduled measurements | 750 results/s of signal time | 7,500 results define the ten-second target |
| Sustainable FPGA measurement profile | 30 MS/s input; one pilot every 10 frames (75 measurements/s) | 751 measurements span exactly 10 seconds and stay below measured ARM drain capacity |
| Exported IQ and ARM acquisition | 2.5 MS/s | Continuous GLI1 stream in original 30-MS/s coordinates |
| ARM coarse authority observer | 2.5 MS/s, one pilot every 9 frames (83.33 measurements/s) | Up to 1,024 measurements and 12 seconds of source span |
| ARM native-result retention | Measured about 96.5 results/s in run-v4 | Drains FPGA heads through sysfs; it is slower than signal time |
| Long controller wall deadline | 120 s | Time to drain already authorized results; it does not enlarge the ten-second source horizon |
| Whole worker | 300 s | Fixed total bound; operator alarm is 325 s |

The measured run-v4 drain rate projects 7,500 results in about 77.7 wall
seconds, but the source advances ten seconds while ARM drains only about 965
results. Later dense jobs therefore become late before they can be submitted;
the 120-second wall deadline cannot repair that causal backlog.

The sparse profile has about 21.5 results/s of measured drain margin. A
15-frame/50-Hz prototype was rejected before deployment because it leaves only
seven observations in the estimator's 96-frame causal window; the estimator
requires at least eight. Ten frames is the slowest cadence that retains useful
model margin while remaining below the ARM port capacity.

## Sparse-cadence physical runs

| Run | LO | Exported-IQ time | Searches | Handoffs | Longest source span | Evidence review |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| sparse-v2 | 1.9403125 GHz | 122.887 s | 126 | 4 | 428 measurements / 5.693 s | Fails: retained 33-frame stale authority |
| sparse-v3 | 1.9403125 GHz | 221.413 s | 256 | 0 | none | Clean negative dwell |
| sparse-v4 | 1.1903125 GHz | 222.219 s | 256 | 1 | 158 / 2.093 s | Fails: retained 33-frame stale authority |
| sparse-v5 | 1.4403125 GHz | 225.942 s | 256 | 3 | 15 / 0.187 s | One 2-result journal passes; later journals expose the stale refresh |
| sparse-v6 | 1.6903125 GHz | 221.557 s | 256 | 0 | none | Clean negative dwell |
| sparse-v7 | 1.9403125 GHz | 227.443 s | 256 | 2 | 124 / 1.640 s | **Both journals pass independent review** |
| sparse-v8 | 1.9403125 GHz | 211.019 s | 256 | 0 | none | Clean negative dwell after authority fix |
| sparse-v9 | 1.9403125 GHz | 219.559 s | 256 | 0 | none | Clean negative dwell after authority fix |

The eight dwells total 1,672.040 seconds (27.867 minutes) of exported-IQ time,
inside the 30-minute collection cap.

All sparse terminals were clean acquisition loss rather than controller
deadline. The strongest v2 episode scheduled and drained 428 results without
falling behind source time. Of those, 12 pass the unchanged native diagnostic
gate; most other pilots report low coherence (rejection 64), with 80 also
outside the local timing window (rejection 96). Sparse-v7 retained and popped
all 199 configured results, passed cadence/descriptor/head/estimate
association, drained and cleared the FPGA, and restored the exact serial,
image, buffers and TX-safe state.

## Physical runs

| Run | ARM binary | Exported-IQ time | Searches | Handoffs | Longest episode | Terminal observation |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| v3 | `e579af79…7850cf4` | 17.629 s | 18 | 3 | 655 / 0.873 s | Exposed premature descriptor-horizon exhaustion; final episode reported source loss |
| v4 | `c8a39148…7b78e1d` | 139.218 s | 183 | 2 | 1,158 / 1.544 s | Horizon fix worked; controller reached the old 12-second wall deadline |
| v5 | `480b6c60…cbe174` | 215.135 s | 256 | 0 | none | Clean negative dwell after the 120-second fix |
| v6 | `480b6c60…cbe174` | 216.013 s | 256 | 0 | none | Clean negative dwell after the 120-second fix |

Run-v3 episode lengths are 193, 655 and 65 results. Run-v4 episode lengths are
323 and 1,158 results. Run-v4's final episode ended with a controller deadline,
after all 1,158 configured results had been retained and popped. Its native
journal independently decodes with 416 supported results; the observer records
124 supported measurements out of 130. Runs v5 and v6 completed all 256 bounded
search attempts without creating native work. They are negative signal dwells,
not evidence that an acquired track failed.

All four final GLI1 snapshots pass the capture fault/loss checks. Every operator
record confirms the same serial and image after execution, no enabled IIO
buffer, TX LO powered down, and TX gain at -80 dB. Temporary remote files were
removed. Run-v5's independent epoch/ownership review passes with its empty
native journal. The older review schema deliberately does not classify the
run-v4 deadline as a successful episode; the individual journal and capture
checks are reported without promoting it to acceptance.

## Implementation

Firmware branch `codex/radio20-tracking-qualification` contains:

- `67260ed21`: separate retained coarse authority, immutable submitted jobs,
  reconstructed journal authority, and positive/noise/zero controls;
- `ede05fb9e`: descriptor counts use the newest valid authority horizon,
  including a partial final batch;
- `aa8d4070d`: separates ten seconds of source work from the 120-second ARM
  drain deadline and records both limits accurately;
- `fc77d57dc`: adds the opt-in 75-Hz sparse cadence, explicit retained cadence
  evidence, independent reconstruction, operator admission and ARM profile;
- `627654e9c`: rejects observer authority more than 32 frames behind the next
  descriptor frontier.
- `7593b7f6d`: carries the sparse cadence and 751-result target through the
  bounded multi-visit operator;
- `bb8744243`: adds a radio-local 16-result scout across two to four LOs and
  launches one 751-result sparse follow-up on the first proven signal.
- `ac6984526`: also launches refinement from a retained scan64 activity peak,
  leaving scan80/local-2 and all native tracking gates unchanged.
- `f80841de7`: adds the bounded production operator for one activity-triggered
  cycle, SSD-first evidence, exact restoration and hash-verified RAID copy.
- `ee14bf8ad`: adds a non-RF dry run that validates and prints the exact cycle
  before the radio lease can be claimed.
- `fe11b582c`: lets the selected long child use the existing bounded
  reacquisition path while keeping scouts as single visits.
- `1212d9227`: preserves explicit clean loss after those restarts are exhausted
  and downloads raw evidence before parent-status decoding.

The prior focused suite passes **527 tests**. The sparse change additionally
passes 319 controller/journal/operator checks and all 171 live-probe checks; the
post-review admission fix passes 222 controller/journal checks. The corrected
ARM executable SHA-256 is
`32155cdd3cd376ac23e458b71ae40e2ccfebe55e1fa90321f8f328a695485f51`.

The radio-local composition accepts the opt-in
`sparse10-after-scout16` plan. All scouts share a 60-second deadline. A proven
scout selects its LO, and one sparse follow-up then has a 320-second deadline;
the whole ARM process has a 400-second alarm. Its result JSON distinguishes an
exhausted scan, a started follow-up and a completed 751-result track. It accepts
success only from the child's retained summary after cleanup. Controller,
fork, classification and profile-limit tests pass (220 plus 37 focused cases),
and the cross-built ARM executable SHA-256 is
`fdf8bebec321cf780dd14bcb96adc10363a019f7131d4dada844032b52130c83`.
That exact executable is staged on the attested radio serial at
`/tmp/glrt-cpu-scout-followup-fdf8bebec321cf78`; its remote hash and dynamic
libraries verify, and an invalid-argument preflight exits 2 before IIO access.
The post-deployment buffer is disabled, TX LO is powered down and TX gain is
-80 dB.
Three existing wall-clock-sensitive live simulations failed in one broad run
and passed individually on rerun.

Post-campaign analysis showed why native-handoff-only scouting was too strict.
In the historical scan64 corpus, a normalized single-pilot power floor of 0.04
within the six attempts ending at a handoff covers four of five handoffs. The
new campaign contained 57 such observations in 32 scout children, including 29
observations at 1.4403125 GHz, but no scan64 native handoff. The revised parent
therefore treats one retained power observation at or above 0.04 as an activity
trigger. It then runs the stronger scan80/local±2 sparse child, whose unchanged
resolver and native gates decide whether tracking exists. Activity is never
reported as a completed track. The strict retained-journal parser rejects
missing, duplicated, nonfinite and oversized evidence; the revised focused
suites pass 415 cases. The final ARM binary SHA-256 is
`c5d4528708e1ad4fdc7c2c7cc9712ec145a77d8289c264374908a6e7c6d756de`.
Its staged payload identity and runtime linkage passed, and the physical cycle
restored the bound serial, image, disabled buffers and TX-safe state.

Replaying the new trigger over all 45 physical cycles would have launched
refinement in 22 cycles. Seven cycles had activity at more than one LO. With
the proposed 1.4403-first order, the first selected LO would be 1.4403 GHz in
15 cycles, 1.1903 GHz in five and 1.9403 GHz in two. This replay predicts trigger
behavior only; it cannot predict whether scan80 would complete 751 results.

The next cycle is now a concrete reproducible command rather than a temporary
harness. `qualify_glrt_cpu_radio_local20.py` admits only the reviewed image,
binary, bank, references and upper-edge LOs; proves the 335.1773184-second
worst-case source bound; validates the exact executed scout/follow-up archive;
and rehashes the SSD-to-RAID copy. Its pure operator and controller coverage
passes 239 focused tests. A suggested LO order is 1.4403125, 1.9403125,
1.1903125, then 1.6903125 GHz because the first LO contained 29 of the 57
campaign observations above the activity floor.

The actual dry run passes with that order, the bound radio serial, reviewed
deployment receipt and all three payload hashes. It declares 335.1773184
seconds maximum source time, SSD output
`/srv/postgres-nvme/codex-radio20-authority/activity-followup-20260915-v1`
and the corresponding hash-verified RAID destination. The focused suite now
passes 240 cases. The dry run performed no RF collection and created neither
output path.

## Radio-local scout campaign

The composition subsequently ran on the physical radio in 45 bounded cycles
split across four admitted tranches.
Each cycle visited all four reviewed upper-edge LOs in the order 1.9403125,
1.1903125, 1.4403125 and 1.6903125 GHz. All 180 child scouts ended with status 0,
`worker_complete=1`, six acquisition attempts, no handoff and no native result.
The parent therefore exhausted each plan cleanly and correctly launched no
sparse follow-up.

The children retained 211,900 source blocks, or 1,388.70784 seconds
(23.1451 minutes) of 2.5-MS/s IQ equivalent, across 1,080 acquisition attempts.
The campaign stopped within the 30-minute RF bound. It produced no candidate
track, so it cannot establish the requested ten-second result.

Each tranche's before/after radio attestations are identical: serial and boot identity,
30-MS/s image and FIT hash, every buffer disabled, TX datapaths absent, TX LO
powered down and TX gain at -80 dB. All 2,074 manifest-listed evidence files
were written to SSD and copied to the `radio-local-scout-followup-20260915-v1`,
`-v3`, `-v4` and `-v5` directories beneath
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912`.
Each SSD and RAID SHA-256 manifest matches; the four RAID copies total about
1.2 GB. The `-v2` name records an admission refusal and contains no RF run.
The compact campaign totals are retained in
[`radio_local_scout_summary.json`](2026_09_15_radio20_30ms_authority_tracking/radio_local_scout_summary.json).

## Activity-triggered follow-up campaign

One initial attempt was refused before RF because the normal acquisition
service held the shared lease. Ten admitted cycles then ran from SSD-first
operator paths `activity-followup-20260915-v2` through `-v11`. Seven exhausted
their two- or four-frequency scouts without activity. Cycles v3, v10 and v11
crossed the retained 0.04 activity floor and selected a sparse follow-up. V3
used the original single-visit wrapper and retained one 15-result clean loss.

V10 physically exercised the newly enabled restart path, but its exhausted
loss surfaced as an unrecognized parent result. The operator still restored
the radio, but decoded the parent before retrieving the archive, so the remote
child journals were cleaned without a host copy. This evidence-loss defect is
fixed and covered by the final v11 run.

V11 selected 1.9403125 GHz and retained four independently decodable native
journals. The epoch/ownership reviewer passes all 74 results, all 64 paired IQ
records, three reacquisition transitions and every final zero-drop snapshot.
The four native episode spans are 0.213, 0.320, 0.200 and 0.200 seconds. The
concurrent ARM observer retained 81 measurements. The parent returned explicit
clean loss after the bounded third restart and did not promote the run to a
completed track.

V12 failed before radio attestation or RF collection because its selected host
Python environment lacked the SSH transport dependency. V13 used the reviewed
environment and the cadence-authority fix from firmware commit `9c8ca3952`.
The two scouts at 1.9403125 and 1.4403125 GHz retained activity but no native
handoff; the radio-local parent selected 1.4403125 GHz and launched the long
follow-up. Its 189th acquisition attempt produced one native episode that
completed all 751 measurements without a restart. Independent review reports
466 supported native diagnostics, 285 rejection-code-64 diagnostics, 699
monotonic coarse-authority refreshes, and a 10.000-second frame span. The
successful child processed 27,326 source blocks and returned status 0 with
`worker_complete=1`.

Every complete admitted cycle has matching SSD and RAID manifests. V10 is
explicitly marked incomplete because only its parent stdout and before/after
operator receipt survived. The reproducible cycle summary and plot are
generated by
[`analyze_activity_followups.py`](2026_09_15_radio20_30ms_authority_tracking/analyze_activity_followups.py)
and retained in
[`activity_followup_summary.json`](2026_09_15_radio20_30ms_authority_tracking/activity_followup_summary.json).

## Evidence and acceptance

The four runs were written to NVMe first. All 51 evidence files were then copied
to
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/authority-track10-30ms-20260914-v1`.
The SSD and RAID SHA-256 manifests match for every file; the 246-MB RAID copy
contains `SHA256SUMS`, and the SSD originals remain in place.

The sparse runs were likewise written to NVMe first and copied to
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/sparse10-30ms-20260915-v1`.
All 106 SSD and RAID files match by SHA-256. The RAID copy is 684 MB and contains
its reproducible `SHA256SUMS`; SSD originals remain in place.

The complete activity-triggered cycles are stored under matching
`activity-followup-20260915-vN` paths on NVMe and RAID. V11 contains 26 retained
files, and its entire RAID manifest verifies. V13 contains 34 retained child
files; all 38 manifest entries match independently on both SSD and RAID. Its
before/after attestation is identical, including serial, boot ID, 30-MS/s image,
FIT/QSPI hashes, disabled buffers and TX-safe state. V10 has no RAID copy for
the documented pre-fix evidence-ordering reason.

The acceptance gate remains:

1. two repeatable dense episodes of at least 7,500 results/10 seconds, or two
   explicitly sparse episodes of 751 measurements spanning 10 seconds;
2. clean loss and reacquisition;
3. zero active capture, CDC and pacer drops;
4. exact radio and TX-safe restoration.

This campaign establishes sustainable 30-MS/s FPGA scheduling, causal authority
admission, zero-loss capture, clean negative behavior and restoration. V13 is
one qualifying sparse ten-second episode, so the single-run milestone is
**passed**. The stated acceptance gate asks for two repeatable episodes, so the
repeatability gate remains open until a second independent 751-result run.

The next stable step is analysis and replay of v13, followed by one independent
repeat rather than changing the native diagnostic threshold. The physical
system now scans, selects an LO, acquires, schedules 30-MS/s FPGA measurements,
uses retained ARM history through native cadence gaps, and drains a ten-second
run without host feedback. Native support is 62.1% in v13; that remains useful
signal-quality evidence and is not relabeled as 100% continuous RF support.

The figure and `summary.json` are regenerated by
[`analyze.py`](2026_09_15_radio20_30ms_authority_tracking/analyze.py) from the
original hash-verified RAID evidence. The sparse figure and
`sparse_summary.json` are regenerated by
[`analyze_sparse.py`](2026_09_15_radio20_30ms_authority_tracking/analyze_sparse.py)
from the sparse RAID evidence.
