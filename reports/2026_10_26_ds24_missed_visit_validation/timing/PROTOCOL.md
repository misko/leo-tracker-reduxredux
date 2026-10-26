# Round2 compact timing/frequency qualification v2

Source preparation only. No outcome run until predictor/source/control/reader
and exact forecast hashes are frozen and root authorizes the stage. Keep all
round1inference sources/results immutable; no validation target outcomes yet.

Primary comparison is ONE consistent primary linear timing point versus ONE
conservative primary quadratic/fallback point, on identical full20ms samples.
The third legacy-adapter linear point is descriptive and reproduces the old
extra rate*0.010s epoch advance. Never pick the highest target score among
methods or combine their acceptances. Operational method is quadratic/fallback;
point linear and legacy have separate control outcomes. Missing donors remain.

Use exactly the sealed round1owned GLRT64 math: same public templates,16tap
fractional sampling, normalization and full512bin frequency profile. One
full-window point per method, zero timing/mode search. CFO dechirp uses the
earlier linear rate at each frame; returned CFO and innovation use the explicit
target-midpoint reference. Consistent timing uses predictor's nominal
midpoint-effective epoch relative to target origin, without another advance.
Retain origin/end timing values and maximum constant-epoch approximation.
Nominal midpoint is not established sample-weighted time; validator review is
requested before freezing. This is not a claim that r01/r02 differ only in
quadratic curvature: data exposure, mode policy and timing reference differ.

Keep margin>=0.025 and earlier declared CFO-halfwidth compatibility as separate
pilot/admission outputs; no donor posterior or precision weight. Preserve
candidate CFO, prior CFO, raw innovation, exact bin spacing443.892045Hz and
grid origin modulo that spacing. Carry is a copied estimate, never fresh data.
Compare actual innovation/carry error in known truth, not gate counts alone.

Proposed compact independent known-signal screen:192full20ms later Gaussian
targets:2edges x2strengths(-12,-24dB) x2true CFO rate signs(+/-2000Hz/s) x6donor
CFO errors[-2500,-750,-0.5bin,+0.5bin,+750,+2500]Hz x4timing errors
[-3.5,-0.5,+0.5,+3.5]native samples. The +/-3.5cases approach a half8sample
coarse cell; +/-0.5are half-native-sample errors. True timing rates+/-100samples/s
and acceleration+/-8samples/s² share the CFO-rate sign. Explicit earlier and
target midpoint counters differ by0.354s. All trial noise vectors independent;
truth only generates/evaluates samples, never chooses a method. This is a
scorer sensitivity/frequency-information control, not a proof of forecast
accuracy. Prediction owner separately owns known-curvature causal-fit tests.

All three method points are identical in these pure scorer controls to avoid
confounding model error with actual frequency innovation. Separate paired
natural earlier-only methods test linear/quadratic/reference differences.
Report strengths, timing offsets, CFO error signs/magnitudes, admitted/unavailable
cases, <=100Hz/<=500Hz accuracy, and every admitted>1kHz failure.
Report conditional admission accuracy and availability separately. The
half-bin-origin cases must show quantization/ambiguity rather than a false
claim of fine uncertainty. Errors beyond500Hz ensure earlier carry alone fails.

Root's pre-outcome clarification: the primary frequency/availability screen is
the48strong-12dB targets with timing error+/-0.5sample:>=90%must be admitted
ANDwithin500Hz. The48strong+/-3.5sample cases are an explicitly labeled timing
mismatch stress stratum, not a claim that one point repairs arbitrary timing.
Require no admitted>1kHz error over all96strong cases; report every weak
catastrophe and all unavailable cases. Root's separate80target round1half-cell diagnostic is reused
as context; no repeated timing-bank experiment is run here.

Proposed nulls:128independent full20ms Gaussian targets,64per edge, one fixed
primary earlier proposal per arm; identical-point sensitivity stratum plus
fixed distinct linear/quadratic/legacy timing-point stratum,32per edge/stratum.
Repeat all descriptive method evaluations; report each method and union, but
the union is not an operational acceptance policy. Wrong symbol-roll17 pilot
controls:32independent targets,16per edge, same method exposure. Frozen
practical null screen remains observed<=5%, exact one-sided95%upper<=10% in
each applicable32trial stratum; no deployment or natural-interference FAR claim.

Development raw stage reuses exactly288paired windows/576owners from round1.
Reuse old paired blind-candidate parity only with identical source/index/IQ
authority, historical runtime, and complete old per-window receipt. Always
exhaust the public reader and verify current acquisition, target and native IQ
hash; do not rerun production_glrt at these already-verified windows. Record
reader/verification time and each new score time separately. Compare original
round1context and random-split search results separately, with all unavailable
states and native ownership. No automatic replacement of valid baseline owners.

Each numerical shard<=580s with BLAS1, at most2workers here. Proposed controls
are a few seconds of full-window scoring, raw replay a bounded twelve-case
stage with exact per-window checkpoints. No new RF, QNAP writes, production
edits, position execution, git mutation or third tuning prototype.
