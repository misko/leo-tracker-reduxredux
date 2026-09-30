# Does improved receiver combining validate the public parity relation?

No consistent transfer is demonstrated. The known-tail recovery improvement
does not make the frozen public-reference equation a validated header check.

The equation remains unchanged:

`sign(symbol 3, bin 524) XOR sign(symbol 3, bin 537) XOR sign(symbol 5, bin 524) = 1`.

It was selected previously using the public reference, not DS10. This test uses
the later header frames and the equal/weighted soft estimates exported by
`receiver_combining.py`. Equal-average exports are checked exactly against the
original receiver caches. All input artifacts and the script are hashed.

| Visit | Frames | Equal-average satisfaction | Marginal baseline | Weighted satisfaction |
|---|---:|---:|---:|---:|
| v1085 | 23 | 65.2% | 67.3% | 65.2% |
| v1150 | 9 | 55.6% | 45.7% | 77.8% |
| v1162 | 11 | 54.5% | 49.4% | 18.2% |

The weighted v1150 result exceeds its cyclic first-constituent controls, but it
has only nine frames and does not reproduce in the other visits. No fit or
method is selected based on these outcomes. This isolated result is not a
validated transferable parity equation or justification for bit correction.

Using the median absolute-amplitude thresholds learned from earlier known-tail
samples leaves only 2, 0 and 1 full three-position checks for equal averaging.
The two nonempty sets satisfy the equation, but their marginal baselines are
also 100%: they contain no demonstrated changing parity information. Stronger
equal-average thresholds leave zero checks in every visit. Thus the apparent
tail reliability benefit cannot support a high-confidence header parity claim
on these data.

Controls keep the target frame's eligibility mask fixed while cyclically
shifting the first sign constituent. They do not preserve the donor's amplitude
eligibility; they are descriptive, not calibrated significance tests. Frame
and coordinate dependence, small sample sizes, and prior evaluation reuse also
limit interpretation. No equation was used to force a sign or correct errors.

The semantic bottleneck persists: we have measured changing signs and improved
known-pattern recovery, but no verified coding, interleaving or field mapping
for the extra region. Conditional satellite association does not identify those
bits. This experiment closes the immediate hypothesis that the demonstrated
combining improvement alone is enough to validate the available public equation.

`combined_parity.py` writes ignored `local/within-visit/combined-parity.json`
with every sign tuple, threshold, frame, comparison and input digest. A synthetic
test verifies that amplitude gating retains both successful and failed parity
checks and correctly handles empty coverage. Test and Ruff pass. No new RF,
manifest changes, commits or remote publication occurred.
