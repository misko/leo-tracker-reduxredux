# Pair-bound multiplication experiment

Replace the pair prefilter's separation/divisor comparison with separation
against a multiplied threshold. Keep the existing scientific guard and expand
the threshold by 2^-48 to retain uncertain rounding cases. The full scorer,
subset bound, search budget, track input and satellite authority are unchanged.

The control and prototype use ordinary O3 builds with identical research flags
(subset/planned/capped/horizon/endpoint-bank/immutable); neither uses PGO.
The four measured ARM runs use control/prototype/prototype/control order,
the existing 16 heldout sites, two search workers and 60-second process limits.
`payloads.json` records verified device hashes. `control-heldout_bound.hpp`
and `prototype-heldout_bound.hpp` preserve the two implementations.

The host research unit suite passes, including 200,000 randomized conservative
rejection checks spanning very small and large magnitudes. The complete fresh
400-point host search JSON equals the qualified prevalidated-stencil control.
Physical ARM results and the adoption decision are recorded in comparison.json.
This experiment alone does not establish full ARM search timing or sustained
pipeline cadence.
