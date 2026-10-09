# Fixed-bank queue comparison frozen after successful reconstruction

The reference-free DS18-022 preflight completed in 12.7397 seconds, reconstructing
2,299 observations and the full 877-satellite regional bank. Its immutable receipt
binds the full observation, bank and prior identities and the production Python
3.14.4 / NumPy 2.4.6 runtime. No likelihood or optimizer was called by preflight.

The final search protocol SHA256 is
`a7abf0bfe414690e1d643e8b01c2b2663361dc6687adc6ab3d49cc52866cf5fe`.
It binds 1,539 source files and five inputs, including the successful preflight
receipt. All 41 synthetic preparation tests pass under that production runtime.
The earlier preparation documents remain historical; this receipt records the
subsequent freeze without changing their bound contents.

The consumed mechanism pilot compares native versus whole-bank queue scores in
both c arms. Each search has the same ordinary 40/20/10/5 km hierarchy and
400-point cap. Original coarse receipts are reused with explicit provenance;
their post-search recovered replacements are not injected into the queue.
The comparison has at most twelve total 500-second slices, with soft deadlines
between operations and cumulative elapsed accounting. Failures and unfinished
searches remain explicit. Imported fitted-c computation and fresh zero-c fits
are not presented as four fresh equal-time searches.

This is a search-allocation experiment. Operational recovery, calibration and
final position fitting are outside its scope and require a matched continuation
before any localization-benefit claim. Known coordinates remain evaluation-only.
Production B7 is unchanged, and the 0.4 km mean-error goal remains unmet.
