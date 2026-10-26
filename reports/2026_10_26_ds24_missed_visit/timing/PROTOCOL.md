# Timing search and disjoint random-frame confirmation v1

Freeze this document, scorer/adapter/harness/tests, prediction source/panel/
packets/donor authority, qualification protocol, split and historical authority
before numerical outcomes. Root must confirm the final receipt before controls
or IQ outcomes. Development only:12recordings,6channels (CH1/4 controls,CH5..8),
4metadata fractions,288paired20ms windows/576RXcells. No validation target
outcomes, GPS, position, new RF, production edits, QNAP writes, commits or push.
Each independent process has580s alarm and BLAS1; at most2workers here. No sweep,
unbounded retry, outcome-based replacement, or disguised multi-hour campaign.

## Single frozen method and controls

Retain up to8causal earlier modes in the prediction packet's original order,
including one-donor fallback and missed visits. Mode cap overflow fails closed;
no silent truncation. Every mode searches the same **fixed** +/-256native-sample
domain at8sample spacing (65points), regardless of its heuristic timing width.
Disclose when the earlier width exceeds this cap. Pick the highest search-frame
exact-minus-control margin across the full bank, then refine that mode's coarse
winner by +/-8samples at1sample spacing, clipped to the original domain. Keep
every tested location, including repeated coarse/fine locations. Final selection
is highest margin, then original mode order, then smallest absolute offset,
then signed offset. At most537search scores (8*65+17) and one operational
confirmation per native target owner. Fine search cannot extend the domain.

Use owned GLRT64 math, public pilot templates and public16tap Lanczos sampling.
At zero CFO rate, all-frame owned math must match public historical
conditioned_glrt64_score (both edges, integer/fractional/wrapped geometry).
Keep the unchanged512bin residual-frequency FFT and exact/control coherent
normalization. Do not revive the failed donor-posterior estimator. Broad residual
CFO search remains the full historical +/-113.6kHz domain; a gatepass can follow
a different pilot far from the donor. Pilot confirmation and earlier-continuity
compatibility are distinct outputs.

Random native intervals of exact frame-period length are anchored at the primary
earlier-predicted epoch minus half a period. Keep only complete intervals inside
the20ms target. Assign half to search and the rest to confirmation by SHA256 of
seed2026102603/stable source-RX-counter owner/interval ID. The partition depends
on earlier metadata only and stays fixed across every mode/timing location.
Only complete64symbol pilot blocks and their interpolation guards wholly inside
one interval enter its group. Discard crossing blocks explicitly. This yields
disjoint raw support over the entire bank, including alternative modes. Every
group needs at least2complete blocks. All native intervals and selected block
envelopes are exported; tested bank geometry is reproducible from source, epoch,
offsets and interval ownership. No IQ values from confirmation enter nomination.
Seal the chosen mode/timing and selection hash through a callback **before**
computing confirmation. A redaction test alters all confirmation samples and
must leave the selection receipt exactly unchanged.

Prediction timing is originally referenced at target start. Advance it by
timing_rate*0.010s to target midpoint, then retain this constant epoch throughout
the20ms scorer. Report the approximation, bounded by2samples over +/-10ms at
the predictor's200samples/s limit. CFO is already referenced at the prediction's
explicit midpoint counter; advance its rate to each pilot frame midpoint before
correlation. Export the unchanged residual-bin CFO at that common target-midpoint
reference. This is a linear dechirp based on earlier rate, not a fitted posterior.
Preserve original start/midpoint references and all donor IDs/support/sources;
native generations come from public raw index authority, not stream labels.

Primary practical support is confirmation margin>=0.025 plus
abs(confirmation_CFO-earlier_predicted_CFO_at_reference)<=the packet's declared
CFO_half_width_hz. These widths are heuristic, not probability calibration.
**Search margin is diagnostic only**, not a second0.025requirement. Report raw
pilot_confirmed separately from continuity_compatible and admitted. Report
search/confirmation CFO difference without a target-chosen agreement tolerance.
No confidence weight is qualified. A donor or alternative is never an additional
independent Doppler point. Later track/association qualification is root-owned.

The sparse point control selects the best ZERO-offset proposal across the SAME
earlier modes using search frames, seals that mode and confirms it once. It
uses the same random ownership and unchanged confirmation policy; it has no
timing search. Thus the primary comparison varies only the timing bank, not
mode selection. Archived original
full20ms detections remain a separately labeled baseline context on identical
physical windows. They have different full-window exposure, and neither old
winner nor its timing chooses an operational mode or offset. Raw support and
the extra search computation are reported instead of claiming equal compute.

## Frozen known-truth and null controls

Independent proper complex Gaussian target vectors,10MHz/200000samples, actual
0.354s revisit. Digital pilot/background ratios-12strong,-18moderate,-24weakdB;
both edges; true CFO rates-2000/+2000Hz/s; donor CFO errors-200/+200Hz; target
start timing prediction errors-256,-97,0,+97,+256samples. For every combination
test zero-rate one-donor fallback and correctly propagated-rate mechanism lanes.
All240target draws are independent (seed2026102604);80strong trials. True CFO
is213456.75+rate*(.354+.010)Hz at target midpoint; timing drift is+/-100samples/s
with the same sign as CFO rate. Strong scalar frequency screen uses all80strong
trials:>=90%within500Hz and no admitted>1kHz error; report availability, timing
error,100Hz/500Hz accuracy and all weak failures separately. The correctly
propagated rate is a labeled mechanism control, not evidence of natural rate
prediction. Truth exists only in waveform generation/evaluation, not the scorer.

Additional out-of-domain timing errors-280/+280samples, strong-12dB, both edges,
both rate signs/errors/forecast lanes:32independent trials. These characterize
the frozen boundary (seed2026102607) and remain separate from the in-domain qualification screen.
Include wrong pilot symbol-roll17 at-12dB, both edges,1and8modes,8draws per cell:
32independent controls. Recorded interfering pilots can be real signals; wrong
injected identity and false confirmation are not interchangeable.

Conditional Gaussian nulls, seed2026102605: both edges,1and8mode exposure,
32independent later vectors per edge/exposure cell,128vectors total. Modes have
fixed distinct earlier-only timing phases/CFO centers, all with the full timing
bank and identical nomination/confirmation rules. Count one boolean per target
per method, including any proposal exposure, for raw pilot confirmation and
continuity admission. Point and search share each null target. Also report their
union, not only a selected method. Exact one-sided95%binomial upper bounds per
edge/exposure stratum and pooled exposure strata; practical screen observed<=5%
and upper<=10% per applicable stratum,>=32independent draws. Finite conditional
Gaussian FAR is not deployment FAR or a288-window family-wise guarantee.

## Development raw stage and positive power control

Root confirms controls/raw stages. Freeze one per-recording numerical shard
(24paired windows,48RXcells) with580s cap. No outcome-based replacement. Every
raw window uses public FastSegmentSource, exact native index/source authority,
full reader exhaustion and full paired original candidate parity. Record failures
and missing donors; repeated index/chunk verification is not raw IQ publication.

After operational point/search selections and confirmations, choose the first
original-rank complete archived candidate passing the old gate, solely for
**evaluation-only** timing/CFO positive control. Score that unchanged archived
anchor with public full20ms and owned all/search/confirmation groups (zero rates,
its original start epoch). Same native partition as operational search, or a
metadata-only epoch0partition if no donor exists. Export full score parity and
all group margins/frequencies/counts. This measures lost power from splitting
and wrong timing/CFO prediction independently. Never feed oracle fields back to
selection. Keep original absence and all failures in denominators. No change to
gates or domain follows these outcomes; root owns any separately frozen round2.
