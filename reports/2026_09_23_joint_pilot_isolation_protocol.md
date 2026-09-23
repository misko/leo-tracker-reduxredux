# Joint pilot isolation: bounded development replay protocol

Status: reviewed pre-IQ protocol. Commit this file with the executable and
synthetic tests before real-data extraction; do not modify the frozen method
after inspecting held responses.

## Question and scope

Do the six metadata-selected opportunities contain two independently useful
known-pilot waveform components, after jointly accounting for the other
component? This is a source-isolation development test. It is not an orbital
fit, phase calibration, satellite identity test, or independent validation of
the metadata selection, which already inspected scores from these samples.

Use only `cap-20260825T010019-89c2889553e0`, stream-1, at 2.5 MS/s, RX0/RX1,
and the six probe starts in
`figures/2026_09_23_independent_phase/geometry-sensitivity/raw-candidate-opportunities.json`.
Read exactly 50,000 samples per receiver per opportunity (20 ms): 120 ms total
capture duration. Use the read-only verified RecordingStore API. No new RF
collection, retuning, or writes to the recording store.

## Frozen choices

Use the sole timing-compatible component matching in each opportunity; fail
closed if it is not unique. Within each component nominate its lowest candidate
rank before IQ access. Do not resolve aliases by favorable held outcomes. Keep
each receiver's archived integer pilot epoch and nominal CFO. The nomination
is a bounded hypothesis and can be wrong; a failed result does not reject all
other aliases or prove signal absence.

Synthesize the repository's upper-edge Qin pilot template at the actual
750 Hz frame lattice, with integer starts computed by rounding each frame
offset independently. Do not repeatedly add a rounded 3,333-sample period.
Each source uses its own epoch. Carrier phase is referenced to sample zero of
the snippet, with the absolute capture start persisted. Do not connect phase
between these isolated snippets.

Split physical sample groups at random, with seed 20260925 plus the zero-based
opportunity index in ascending time order, identically across
the two receivers and both source hypotheses. Group size is 250 samples
(100 microseconds). Remove 16 samples at both ends of each group. Half the
groups train and half are held. Score all guarded samples, including template
zeros, with identical physical masks across receivers and models. No filtering or data-dependent mask crosses
the groups. Persist the exact group assignment and sample support hashes.

## Model and controls

Jointly regress the received complex IQ on the two nominated pilot waveforms.
Use eight known pilot-tone columns per source, with one complex coefficient per
tone constant over 20 ms: sixteen complex coefficients in each two-source
model. This allows frequency-dependent channel response without giving each
held group its own phase fit. Fit coefficients and bounded source-specific CFO
corrections using only training samples. CFO corrections use the fixed interval
±2,500 Hz, a 50 Hz grid, and four coordinate updates in the fixed order A,B,B,A,
initialized at zero. Persist training objective, fitted CFOs, coefficients,
boundary hits, column norms, and train/held Gram rank and conditioning.
Held samples must not fit amplitudes,
carrier, phase offsets, masks, or weights.

Compare the joint exact model with each single-source model, exact-A plus
rolled-B, rolled-A plus exact-B, both rolled, and swapped source epochs. Rolled
templates use the repository's fixed 17-symbol control. All models receive
the same applicable training fit budget. Retain every model and opportunity;
do not report only whichever control or receiver favors the proposed method.

Score held squared prediction error and its incremental reduction from each
single-source/control model. Report per probe and receiver; the sample points
and alias members are not independent scientific trials. No statistical pass
threshold is invented. Six selected snippets are insufficient for a new
population-level association or positioning accuracy claim.

## Interpretation and execution boundary

Poor prediction can reflect channel variation, integer timing error,
wrong alias, nonstationarity, optimizer limitations, or an absent component.
Model failure does not establish absence of a second emitter. A positive incremental exact
response must be assessed against all controls and conditioning before phase
extraction is justified. Even successful isolation does not make asynchronous
source phases simultaneous or remove frequency-dependent receiver delay.

Run synthetic two-source and single-source tests before real IQ. Commit the
reviewed protocol, binding, implementation, and tests before opening the six
snippets. Bound execution to a few minutes; stop on a failure without selecting
new opportunities or silently modifying the protocol after held inspection.
