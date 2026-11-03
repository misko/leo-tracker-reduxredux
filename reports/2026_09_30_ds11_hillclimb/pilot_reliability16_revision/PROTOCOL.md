# Training-symbol pilot-frequency stability audit

Use all124 saved training excerpts from the frozen scan16 waveform replication.
No new IQ reads, replacement, waveform-held symbols, geographic reference,
position fit, or orbit update. Preserve the failed original replication gate.

For both fixed pilot windows, replay the full eight-frame frequency estimate,
then estimate from alternating four-frame groups independently using the same
frequency search and gain profiling. Report frequency disagreement and each
group's search-bound status. At the full estimate, report the fraction of
fitting-symbol energy explained by per-frame/per-carrier coherent means.
These are descriptive stability and coherence measures, not calibrated error
bars or signal-detection probabilities. No reliability threshold is chosen
or position measurement removed by this audit.

Bind code, tests, original manifests, measurements and excerpt inventory before
execution. Check saved excerpt byte and array digests. One worker with one BLAS
thread, nice19, capped at180seconds. Write a per-row active marker before work
and a terminal result after each row. On interruption, preserve the active row
as failed and untouched rows as not attempted; do not retry. Report all124 rows.
A process error or replay discrepancy does not silently authorize a new run.

## Engineering revision

The original worker stopped before opening any excerpt: its provenance check
passed a string to a Path-only digest helper. All124 rows were not attempted.
This separate revision preserves and binds that attempt, converts digest
arguments to Path at the two affected call sites, and allows one new180-second
worker under the identical scientific protocol. No observation was measured
or selected in the first attempt, and no numerical result motivates the fix.
