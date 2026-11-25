# Held DS30-0280 carrier check

The frozen polynomial-preserving correction increased strict agreement
from **513 to 516** on the independently held rank-68 DS30-0280
recording, restoring three matches and spoiling zero. The original
half-blend reached 517 on the same set. All three conditions had 524
matches at the loose window. [Forward receipt](measurements/moment-preserving-cfo-0280.json) ·
[Frozen enrollment](moment-preserving-cfo-protocol.md)

| CFO condition | Strict joint matches | Restored / spoiled vs. unedited | Loose joint matches | p95 absolute signed difference, Hz |
|---|---:|---:|---:|---:|
| Unedited | 513 | 0 / 0 | 524 | 236.08 |
| Polynomial-preserving projection | 516 | 3 / 0 | 524 | 236.08 |
| Previous half-blend | 517 | 6 / 2 | 524 | 204.22 |

The original masked rule proposed 558 edits. The installed 20 ms receiver
supplied 541 matching winners and was empty at 17 opportunities. The two
receiver methods can select different peaks at the same opportunity.
All matched pairs enter the signed error distribution. The projection retains 378 nonzero
edits and 619,747.70 Hz², or 23.23% of the previous delta energy. The
maximum residual moment on stored projected CFOs was 6.78e-11 Hz,
within its computed roundoff bound.
[Candidate-only seal](measurements/moment-preserving-cfo-0280-candidate.json)

Both first-generation official acquisition roles finished and verified
in successor-then-installed order. The candidate-only projection was
sealed before opening the installed detector packet. Total offline time
on CPU 3 was 2.820 CPU seconds and 2.902 wall seconds. The masked Graph
used 0.872 CPU seconds, the ordinary Graph replay 1.651, and the
projection 13.4 ms. The study used saved numerical inputs and ran zero
receiver or position fits.
[Forward runner](moment_preserving_cfo_forward.py) ·
[Development comparison](moment-preserving-cfo-development.md)

The held strict agreement change has the same direction as the four
development cases. The result measures carrier agreement against a
separately acquired same-capture reference.
