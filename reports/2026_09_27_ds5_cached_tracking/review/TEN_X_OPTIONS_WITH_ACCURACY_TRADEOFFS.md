# Server 10x options when a small metric loss is acceptable

This review ranks architecture families using the frozen server measurements.
It does not change a detector, open holdout IQ, or claim that separately
measured gains multiply. A faster candidate still needs an explicitly frozen
detection/association/false-alarm objective; the application comparator's
inactive result is not physical absence truth.

## The fallback budget

The frozen TG11 phase-one medians were 94.528x faster than the application at
2.5 Msps and 122.815x at 5 Msps. Those calls used a scientifically different
native detector and failed the old no-extra gate, but their costs give a useful
best-case fast-path budget.

Let the application cost be 1, fast-path cost be `r`, and let fraction `p` of
visits pay an additional complete application fallback after attempting fast.
The whole cost is `r + p`, so 10x requires:

| Rate | Fast ratio `r` | Maximum additive full-fallback fraction `p` |
|---:|---:|---:|
| 2.5 Msps | 0.01058 | 8.942% |
| 5 Msps | 0.00814 | 9.186% |

This is more restrictive than replacing fast with slow on fallback because the
failed fast work has already occurred. If 2% of all visits are reserved for a
random full audit, uncertainty-triggered fallbacks can occupy at most another
7.084% at 2.5 Msps and 7.332% at 5 Msps after overlap accounting. A 5% audit
leaves only 4.150%/4.406%.

Any design that falls back on every fast positive is unlikely to fit. The
earlier 129/256 count came from the older native one-confirmation comparator,
not the current full application scanner, so it cannot supply a full-scanner
fallback fraction or loss denominator. Likewise, a fallback that catches only
obvious low-margin cases cannot be credited with correcting confident misses
or extras. Random audits estimate those errors; they do not repair unaudited
decisions.

The phase-one ratios cannot be used as a performance prediction for canonical
confirmation or for a stronger multi-candidate native detector. They show that
fallback rate and added protection cost, rather than the original fast-kernel
cost alone, will determine whether a hybrid remains above 10x.

## Ranked option families

| Rank | Family | Plausible 10x role | Accuracy or product change | Current evidence |
|---:|---|---|---|---|
| 1 | Interference-protected native TG11 with more candidates and stronger confirmation | Preserves the native tone-nuisance protections while spending part of the 94.5x/122.8x headroom on two or four candidates, coherence and timing consistency. A qualified blind detector can later seed a causal cache. | Still a different detector from the application; losses, extras and pair association require a newly frozen metric. | The original TG11 control stage passed its constructed controls, but phase one produced the unadjudicated v1078 extra. More-candidate/coherence variants remain unmeasured. |
| 2 | Selective full fallback and audit around the protected native detector | Can repair declared uncertainty classes while random audits measure confident errors. | The combined fallback and audit route must remain within the measured additive budget; unaudited errors remain errors. | Original TG11 cost leaves about 8.9%/9.2% for additive full fallback before audit or added candidate cost. |
| 3 | Reduced-window, reduced-grid stateless scanner | Removes acquisition work on every visit, including quiet channels, without requiring history. | Misses signals outside selected windows/CFO cells; lower candidate count loses competing identities. | Acquisition is 81.5%/93.0% of application CPU, so only an acquisition reduction can matter. No reduced configuration is qualified yet. |
| 4 | GPU or many-core batch execution | Strong option for wall latency and queued throughput while preserving a broad search. | Usually does not reduce total operations; FP32/device arithmetic and transfer need scientific qualification. | 22 CPU workers measured 8.20x/10.69x wall speedup but increased aggregate CPU 43%/29%. Eight workers used near-baseline CPU but reached only 6.61x/7.04x wall. |
| 5 | FP32, lower precision, coarser timing/CFO grids | Useful inside families 1 or 3 to lower the dominant acquisition cost. | Peak order, low-SNR candidates and nuisance fits can change. | The paired 320-case native comparison measured 1.4128x against its packed-FP64 baseline. A separate 256-receiver new-data comparison measured 1.620x against its own baseline and retained 129/129 older one-confirmation reference positives. These are different workloads and neither is a standalone 10x result. Rank-seeded acquisition reached 1.94x while losing 28/36 old positives. |
| 6 | Fewer candidates or shorter GLRT aperture | Reduces final confirmation and response size after acquisition. | Competing signals and weak/ambiguous candidates are lost; a shorter aperture changes the statistic. | GLRT confirmation was only 18.0% of 2.5 Msps and 6.8% of 5 Msps CPU. Candidate/aperture reduction alone cannot reach 10x. |
| 7 | Exact early exit and overlap reuse | Safe supporting optimization for a narrow decision API. | Early exit preserves the decision but negatives still run fully; overlap reuse is implementation complexity. | Exact early exit measured 3.874x/1.761x. Perfect overlap reuse ceilings were about 1.25x/1.45x. Neither is a 10x path. |
| 8 | Decision-band decimation | Can reduce high-rate work if anti-alias preprocessing and source mapping are included. | Changes bandwidth/statistic; direct FIR cost and filter boundaries matter. High-rate recall needs a matched native-rate oracle. | Direct FIR cost was about 24-40 ms for both RX and dominated the prototype. A staged/polyphase/FFT filter remains unmeasured. |
| 9 | Visit-wide ambiguity engine | Could share transforms across timing/CFO hypotheses and avoid repeated stages. | New detector statistic and large development effort. | Prior operation counting rejected a full 2-D grid against a 0.260 ms native one-confirmation target. That does not bound feasibility inside the current full-scanner 143/389 ms 10x budgets; no full-scanner artifact exists. |
| 10 | Raw native proposals + canonical integer confirmation | Development diagnostic only until interference protection is redesigned. | The canonical statistic does not inherit native tone-nuisance rejection. | The current prototype activated 6/12 base tone-only receiver controls and 7/84 tone rows including repeated sequences. It is not the best small-loss candidate in its current form. |

## What each trade permits

### 1. Interference-protected fast detector, then cache and bounded fallback

Start from the native TG11 detector because its tone-nuisance path passed the
constructed control stage. Use the available cost headroom to retain two or
four candidates and add coherent timing/confirmation consistency before making
a blind decision. Only a blind detector that passes fixed controls and a frozen
real-data comparison should establish cache state. A cached check still needs
fresh full-aperture evidence and must fall open to discovery when it fails.

The raw canonical integer-confirmation prototype is evidence against replacing
that protection casually. It activated 6/12 base tone-only receiver controls
and 7/84 tone rows when repeated sequences are included. Timing inconsistency
may be useful in a future protection redesign, but that was noticed after the
outcomes and is not a qualified repair. The current canonical prototype cannot
be ranked as the best small-loss candidate.

The completed v1078 diagnostic is decisive: native timing/CFO coordinates at
integer epochs 7 and 9 pass the current canonical scorer with margins 0.1356
and 0.1168, while application top-ten acquisition misses that identity by
48-50 microseconds and 84.7 kHz. Calling this a known false positive would be
unsupported; calling it retained application behavior would also be false. A
new evaluation must distinguish constructed negative controls, injected truth,
application-relative changes, and unadjudicated extra real signals.
The old phase-one science gate remains failed regardless of that diagnostic;
the diagnostic does not retroactively establish physical truth.

If a small comparator-relative hit is acceptable, freeze it numerically before
running. The new diagnostic dataset must first establish and freeze the current
full-scanner reference-positive counts separately at 2.5 and 5 Msps. Express
every allowed loss as an explicit `lost/reference` count at each rate; do not
reuse 129, which belongs to an older native one-confirmation comparator. Require
zero new noise/tone control positives and separately report every additional
real-IQ pair without labeling it false. This remains a development metric, not
a field false-alarm rate. Physical truth requires separate evidence.

For production-style fallback, predeclare an uncertainty predicate using only
fast outputs: unsupported proposal, absent second probe, timing/CFO innovation,
near-threshold margin band, or ambiguity between trajectories. Measure its
route fraction before claiming 10x. With a 2% random audit, uncertainty fallback
must stay below roughly 7.1%/7.3% to preserve the additive budget. Do not tune
the predicate until its misses disappear; confident audited errors remain
errors in the reported metric.

### 2. Selective fallback and audit

Run the complete application only for a preregistered uncertainty class, plus a
small random audit of confident fast decisions. The uncertainty predicate may
use support, pair completeness, competing trajectories, coherence and margin,
but it must be frozen before real outcomes. Every full fallback includes the
already-spent fast work.

The 94.528x/122.815x measurements leave only about 8.9%/9.2% for additive full
fallback before accounting for random audit or the added cost of more native
candidates and stronger confirmation. Recompute this budget from the measured
final fast candidate; do not carry the original headroom forward unchanged.

### 3. Reduced search without cache

A bounded approximate configuration could evaluate two or three fixed
nonoverlapping probes, keep one or two acquisition candidates, use a coarser
timing/CFO grid, and apply an interference-protected final score. It makes every
visit independent and avoids stale-state failure.

Window reduction alone is insufficient. Even a linear two-of-eleven share of
the measured acquisition stage is about 228 ms at 2.5 Msps and 757 ms at
5 Msps, already above the 143/389 ms whole-call budgets before confirmation.
Three windows are about 342/1,136 ms by the same deliberately simple planning
model. The prototype therefore needs an additional acquisition change such as
a much coarser grid or batched low-precision correlation. These are operation
budgets, not multiplied measured speedups.

The smallest useful experiment is three frozen configurations, not a sweep:

1. two probes, top one proposal, protected GLRT-64;
2. three probes, top one proposal, protected GLRT-64;
3. three probes, top two proposals, protected GLRT-32 as an explicitly new
   statistic.

Run fixed injected/noise/tone/mixture controls first. Record temporal coverage,
candidate recall, pair association and extras. Stop before real replay if no
configuration meets the absolute CPU budget or the preregistered accuracy-loss
allowance.

### Adaptive scan cadence

A full scan every tenth opportunity reduces full-scan work by about 10x only if
the other nine opportunities do no comparable analysis. Those nine rows are
`unknown`, not negative and not cached detections. Worst-case discovery latency
becomes ten scan intervals, and a signal shorter than that cadence can be missed
entirely.

A more useful service can run full discovery every `N` visits and execute two
fresh, interference-protected full-aperture confirmations in between. That returns evidence on
established channels but routes unseen/changed channels according to the chosen
cadence. Report separately: full discoveries, confirmed tracked positives,
failed checks, and unknown unscheduled visits. Choose `N` from an explicit
maximum discovery-latency requirement, rather than choosing it after seeing
speed.

Cadence is appropriate only if the product accepts reduced temporal coverage.
It does not satisfy the original all-visits scanner objective.

### Parallel CPU and GPU

The exact 22-worker result is already near a 10x wall-latency demonstration on
one 5 Msps development case. It is the strongest choice when the target is
latency and idle cores are available. It is not compute reduction: aggregate
CPU increased. Eight workers are a better efficiency point but remain below
10x wall speedup.

A GPU prototype should batch the 22 receiver/probe acquisitions, keep IQ and
templates resident for all candidate stages, and return a narrow result. Time
host conversion, transfer, kernels, synchronization and result fold. Report GPU
time and energy separately from host CPU. It may deliver 10x wall latency, but
no current receipt supports that claim and it should not be combined on paper
with early-exit or FP32 gains.

## Recommended next three variants

1. **Protected native TG11 with two/four candidates and stronger coherent
   confirmation.** Preserve the existing tone-nuisance treatment, run all-blind
   controls first, freeze full-scanner reference counts by rate, and measure
   complete CI16-to-decision cost. This is the leading per-visit compute
   candidate; the raw canonical prototype is excluded because of its tone
   control positives.
2. **Add causal reuse and selective fallback to the best qualified blind
   variant.** Establish state only from its causal blind observations, require
   fresh full-aperture confirmation, and freeze both uncertainty fallback and
   random-audit routes. Recalculate the 10x budget using the final protected
   fast-path cost.
3. **Stateless reduced search.** Implement only the three fixed configurations
   above and stop on controls/cost. It provides an independent option for quiet
   or rapidly changing channels where cache hits are rare.

Keep the exact 8/22-worker implementation as the immediate wall-latency option,
consider a GPU batch only after deciding that wall latency rather than total
compute is the governing 10x metric, and retain cadence as an explicit
coverage/latency trade rather than calling unscheduled visits detections.

No recommendation above closes the task by arithmetic composition. Each needs
one end-to-end measurement with its own complete route mix and scientific
contract.
