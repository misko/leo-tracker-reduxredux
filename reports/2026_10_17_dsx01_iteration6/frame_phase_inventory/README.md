# Frame-arrival metadata inventory: all 15 windows available, alternatives retained

All **693/693** frozen observations across all **15/15** windows match their
public source probe IDs and original winning candidate ranks exactly. Every
winning candidate has a finite integer/fractional arrival anchor. No missing
value was reconstructed. The inventory preserves all **4,251 public retained
candidates**, including **2,224 passed candidates**, without selecting a new peak,
clustering phases, unwrapping, fitting phase, or constructing a geometric model.

**551/693 probes have multiple exact numerical fractional phases among passed
candidates; 292/693 have multiple passed integer anchors. These are stored
candidate alternatives, not emitter counts.** Nearby alternatives can be
different estimates of the same timing peak. Neither the original winner nor
the alternatives are independently verified transmitter epochs or identities.

## Per-window availability and alternatives

The last column gives the range of distinct numerical modulo phases per probe
among passed candidates, computed directly from the stored anchors without a
phase-clustering threshold. Counts preserve all original denominators.

| Window | Source | Available / original N | Passed candidate total | Probes with multiple fractional phases | Probes with multiple integer anchors | Fractional phase count range |
|---|---|---:|---:|---:|---:|---:|
| 001 | S01 | 86/86 | 370 | 82 | 43 | 1–7 |
| 002 | S01 | 35/35 | 82 | 18 | 9 | 1–4 |
| 003 | S01 | 27/27 | 150 | 27 | 26 | 2–6 |
| 004 | S02 | 44/44 | 108 | 29 | 10 | 1–4 |
| 005 | S02 | 33/33 | 74 | 23 | 3 | 1–3 |
| 006 | S02 | 72/72 | 196 | 62 | 21 | 1–5 |
| 007 | S03 | 54/54 | 221 | 47 | 42 | 1–6 |
| 008 | S03 | 50/50 | 119 | 25 | 15 | 1–5 |
| 009 | S03 | 34/34 | 105 | 29 | 15 | 1–4 |
| 010 | S04 | 46/46 | 109 | 36 | 12 | 1–4 |
| 011 | S04 | 43/43 | 128 | 41 | 17 | 1–5 |
| 012 | S04 | 66/66 | 218 | 55 | 32 | 1–5 |
| 013 | S05 | 28/28 | 119 | 26 | 25 | 1–4 |
| 014 | S05 | 39/39 | 79 | 15 | 7 | 1–3 |
| 015 | S05 | 36/36 | 146 | 36 | 15 | 2–4 |

Across all probes, passed integer-anchor counts 1/2/3/4 occur in
401/235/51/6 probes. Exact fractional-phase counts 1/2/3/4/5/6/7 occur in
142/255/195/80/17/3/1 probes. Passed candidate counts can reach eight, since
different retained candidates can share one phase. No uncertainty-based
equivalence or distinct-emitter claim is inferred from exact float equality.

Among the 551 probes with multiple numerical phases, the median maximum
pairwise circular separation is only 0.0936 sample, while its 90th percentile
is 1123.39 samples and maximum 1626.00 samples. The minimum pairwise separation
can be about 2.3e−13 sample, a numerically tiny difference. Thus the raw count
mixes nearly coincident alternatives with widely separated timing possibilities.
All values/separations are available for inspection; none is silently merged.
The public narrow candidate port does not supply a calibrated timing covariance
or a verified physical choice among these peaks.

## Exact identity, counters and time axes

`observations.jsonl` contains one record per frozen observation, retaining its
window/source ID and every public candidate. The group identity is the public
canonical digest of capture input-manifest digest, visit index, **contract
receiver 0/1**, and probe index. Frozen human-readable RX1/RX2 labels are checked
against contract receiver+1. Each row exactly checks channel, actual RF and
CFO-support-center time against the frozen metadata export.

The original exported winner is reproduced by the declared highest passed
margin, then candidate rank/ID tie-break; there is no new phase/CFO-trajectory,
satellite or window-dependent choice. This binds the existing winning cohort,
not an independently selected phase peak.

Every source has a nominal sample rate of **2,500,000 samples/s**, and all five
public inputs report qualified counter continuity. Positive arrival phase uses
the audited physical period **Fs/750 = 3333⅓ samples**, not a rounded 3333-sample
accumulation. Per-probe fields preserve exact integer valid-start counters,
session-start counter authority, probe offset in integer milliseconds, selected
integer anchor, fractional offset and the device/session-relative first-frame
integer sample separately. The phase calculation is:

```
C = valid_start_counter - session_start_counter + probe_start_ms*Fs//1000
phase = (((C*750)%Fs)/750 + integer_epoch + fractional_offset) % (Fs/750)
t_first = C/Fs + (integer_epoch + fractional_offset)/Fs
```

Both **first-frame epoch** and **CFO-support-center time** are bound explicitly.
Support centers are 8.816–9.483 ms after the first frame across these 693 rows.
The original support start/center/end UTC estimates are preserved. First-frame
UTC is derived from the existing capture UTC anchor; integer sample authority
and fractional offset remain separate so rounding to nanoseconds is not mistaken
for exact physical UTC. One sample is 0.4 microseconds. This inventory performs
no clock/sample-rate correction and makes no transmitted-cycle or range claim.

`source-provenance.json` records each public job/input/terminal digest, recording
and analysis manifests, raw recording authority, radio/session/stream generation,
capture mode, sample rate and full existing timing authority. Each observation
binds back to those source digests. `regions.json` preserves all per-window count
histograms; `summary.json` records input/code hashes and aggregate counts.

## Validation and limits

Three hardware-free tests pass: multiple candidates remain explicit without
reading CFO or satellite fields; unavailable fractional offsets are flagged
without replacing them with zero; and group IDs bind receiver identity while
the original score/rank rule reproduces its winner. The separately sealed
`frame_phase_audit/phase_math.py` is reused read-only for positive sign,
rational-period wrapping and exact integer counter arithmetic. Its four prior
precision/sign tests remain applicable.

The single bounded metadata read took **14.58 seconds**. No raw IQ, RF collection,
TLE/position model, phase fit, geographic seed, changed source winner or physical
inference was used. Phase evidence is available for every frozen window; a
unique physical epoch/emitter is not established for every probe. Any later
coherence assay must handle the retained alternatives explicitly. This inventory
does not treat frame phase as propagation delay or claim independent identity
validation merely from its availability.
