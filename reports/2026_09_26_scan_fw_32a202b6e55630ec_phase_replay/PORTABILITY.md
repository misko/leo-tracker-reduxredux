# Shared replay portability notes

The production `AdaptiveHopAnalysisSource.read_visit` is the authority for
manifest-bound, digest-verified CI16. The report adapter should wrap it and add
audit masks; it must not duplicate decompression, path construction, or receipt
validation.

Packages D, E, and F can reuse pure estimators from `src/leo/analysis/qam`,
`src/leo/analysis/starlink`, and `src/leo/analysis/research`. Historical report
scripts remain references because several bind fixed recordings, 2.5 MS/s,
300,000-sample dwells, or private paths. Port numerical kernels only after
checking sample rate, receiver, Qin edge, frame origin, filter delay, and phase
reference. Feed each kernel `ReplayVisitArrays` or a smaller array view.

Package D should preserve a single integer device-counter origin across its six
20 ms containers and must carry the fitted phase reference explicitly. Package
E should share one direct/FFT normalization and Parseval test with F, and should
derive 2.5 MS/s through a documented anti-alias transform with its support in
the mask. Package F should begin with zero delay, identity response, and no
fitted evaluation intercept; trained response products must bind development
support and keep raw and response-normalized observables distinct.

Every transform reports its full input support. Use `support_is_disjoint` after
including filter/transform expansion, and use device counters for elapsed time.
Compact stored indices identify bytes only; adjacent stored rows can be
separated by a device-time gap or retune.
