# Subsecond single-core GLRT objective

Target: process a 120 ms dual-RX saved-IQ dwell at 2.5 MS/s in less than one
CPU second on one PLUTO+ Cortex-A9 core, while preserving close to the current
19,400/19,581 original individual GLRT hits on the 704-dwell mixed-rate DS7
benchmark. Preserve support for 2.5/5/7.5/10 MS/s. All 22 receiver-windows
and their candidate multiplicity remain in scope; confirmations are not the
recovery denominator. Aim to preserve all 19,400 and report every additional
loss explicitly. No real-time or capture-headroom claim follows from subsecond.

Previous goal turn made progress: compiler/local tuning was measured at
4.468 search seconds, or 5.319 seconds with separately measured proposals,
retaining 19,400/19,581 hits. It was published as fedf273e7. The goal remains
unmet. This continuation tests structural and numerical changes against that
actual baseline, using frozen IQ and no RF activity.

Independent screens use 32 mixed-rate dwells, 704 windows and 843 original
hits; baseline recovery is 838/843. ARM timing uses four saved 2.5 MS/s
dwells, 88 windows and 119 original hits. Expand promising combined candidates
to 704 dwells and audit final GLRT outputs, not proposal coverage. Test all
rates, partial input and full-scale CI16. ARM component tests and timings run
serially; host timing is diagnostic only. Preserve rejected experiments.

Count conversion, scaling, per-window allocation, FFT planning and cleanup
inside search costs. Treat separately measured proposal plus search time as
a stage sum. A final subsecond claim needs a combined measured pipeline with
all proposal/search work included, bounded setup identified separately, and
repeat ARM runs. No independent speedup ratios are multiplied together.

Use the standard same-window maximum-cardinality one-to-one hit matcher:
margin >=0.025, epoch <=2 samples, tracking CFO <=8 kHz. Report unmatched
positive entries, per-rate recovery, actual windows and actual kernel calls.
The existing 18,328 unmatched positives are a quality limitation, not verified
new physical signals. Production paths and scientific fixtures are unchanged.
