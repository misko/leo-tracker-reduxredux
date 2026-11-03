# Full-support peak search and causal continuity

Freeze before execution. Use all eight visit pilot matrices from the paired-RX
raw replay, two receivers and 80 frames. Verify parent source hashes and
reproduce every original held own-RX error from these matrices before comparing.
Frames 0–29 initialize causal history; score all frames 30–79 (800 cases).

Every arm fits pilots 22–221 and evaluates 222–301. Legacy initializes from
22–121 and locally refines, exactly as in the preceding report. The new global
arm finds the six strongest separated peaks over the full 22–221 pilot support,
using an 8192-point FFT and at least 2 kHz separation, then refines each within
one FFT bin. Profile independent complex carrier gains.

The causal arm selects from the same candidates by normalized explained energy
minus `0.03 * min((wrapped_frequency_change / 500 Hz)^2, 4)`. At the first
frame or when no history exists, use the global best. If its explained energy
is below 0.2, report it but clear history. Strong jumps can overcome the capped
0.12 penalty. All settings are fixed; no held sample or peer RX enters selection.
Frequency wraps modulo 1/4.4 microseconds; no absolute alias identification.

Test signed peak recovery, held-sample isolation, rejection of small transient
peak swaps, acceptance of a strong jump, and reset after low-evidence frames.
Report all cases, per-visit/RX paired errors, number of changed selections and
large changes. Do not equate smoother frequency with improved truth. Candidate
selection must improve held pilots to advance; no geographic jobs in this assay.
