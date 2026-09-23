# Fixed first-six and first-sixteen long-TRAIN searches

Extend the accepted first-scan blind tau-zero protocol without changing its
model or search settings. Use exactly the first six and first sixteen sessions
in frozen long-cohort TRAIN order. Require one corrected response-free compact
cache per session and fail on missing, duplicate, or out-of-order support. Do
not access long validation/test sessions.

For each geographic trial, independently profile each scan's track candidate
identities and constant CFOs from its saved training rows at tau zero. Combine
all tracks across scans with the same duration-weighted capped-800-Hz objective.
No identity, CFO, timing, or receiver parameter is shared across scans.

Run Sacramento 250 km and Reno 500 km separately with the frozen great-circle
search: 100 km grid, three spacing-diverse cells, and 3-by-3 refinements at 50,
25, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, and 0.1953125 km. The three
extra levels are predeclared to remove the 1.56 km grid floor when assessing a
sub-300 m target; they are not chosen from reference error. Report both the
1.5625 km coarse-control incumbent and final trained incumbent. Altitude remains zero. Seal both view/prior
inferences before reserved-row and reference scoring. The first-scan reference
error does not alter this protocol.

This remains conditional on the response-free regional candidate filter,
coarse-beam heuristic, tau zero, altitude zero, and fixed TRAIN views. It is a
development diagnostic, not independent validation or a global optimum claim.
