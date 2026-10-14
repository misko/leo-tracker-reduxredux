# Fixed likelihood-width continuation

The matched phase control did not resolve B's worst cases. The next hypothesis
is an optimization barrier between satellite-assignment modes under the narrow
frequency likelihood. This experiment temporarily doubles observation sigma,
then returns to the exact original likelihood. It changes the optimization
path, not the final scientific score or priors. It is distinct from the earlier
quarter-likelihood weighting test, which changed the final likelihood/prior
balance. No scale sweep or reference-selected schedule is permitted.

Predetermined cases are DS21-039 and DS21-023; each has all/low/high views from
the original shared-discovery B pipeline. Each view starts from its original
stationary training winner, in a new 25 km disk centered on that winner.
Both conditions have two planned 20-second/600-iteration stages: control uses
sigma factors 1→1; alternative uses 2→1. All clock, timing, calibration,
fitted-c, candidate, observation and physical constraints remain unchanged.
An intermediate feasible state can seed the second stage without being
stationary; this is a predeclared optimization chain. Only a stationary final
state under the original likelihood is an accepted position. Failed calls and
unavailable finals remain, with no incumbent replacement or retry.

Each case permits 12 calls and 330 seconds including preparation, with external
TERM/KILL at 345/350 seconds. Source/input bindings freeze before preparation,
and each call receives exclusive launch/result/termination receipts. Both
cases must seal before reference evaluation. Report convergence, original
objective/NLL and position separately. This is a warm two-stage test, not a new
end-to-end six-start comparison or an independent-half baseline.

The original objective replays at each seed and each intermediate returned
state. Component tests require the factor-one null, unchanged priors/design,
unmodified source objects, identical initial states and budgets, and an exact
return to the original objective in both final stages. Two tests and Ruff pass.

A separate metadata-only preflight found no common selected satellites among
any pair of the original five comparison recordings (001/003/005/023/039).
Even 003/005, which share a TLE snapshot, have disjoint selected banks.
Consequently those fits cannot justify learning a shared satellite-specific
timing correction across recordings. No such transfer is introduced here.
