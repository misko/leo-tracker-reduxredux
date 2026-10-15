# C053 profile geography: boundary-active, tangent probes infeasible

The accepted scaled fixed profile remains at its original25 km disk boundary. Its free-geography physical KKT is2.971106, so fixed-profile acceptance does not imply a stationary free-position solution. The geographic gradient is(−19.342257,38.375269) objective units/km; nuisance scaled gradient remains0.000276556. The physical initializer is unchanged exactly.

The inward radial derivative is+42.833035. Both feasible inward probes worsen J: +0.045610 at1 m and+0.706325 at10 m, with zero visibility changes. The projected geographic gradient is tangent, with analytic directional derivative−3.480700. However, straight tangent steps leave the circular disk: radii25.000000020 km and25.000002000 km. Both were explicitly skipped without evaluating or projecting their states.

Consequently this audit has not evaluated a feasible downhill geographic step. It also does not demonstrate absence of feasible descent: a circular-arc path has the same first-order tangent direction while remaining in the disk. Two prespecified arc probes would resolve that admission question before the proposed same-domain free solve. The outward radial derivative is negative, but no larger domain or reference-derived direction is introduced here.

Actual cost3 native objectives and3 explicit orbit predictions, zero fits/reference/held,50.207 seconds scientific preparation/audit; independent135/140 second external bounds. Both infeasible probes are preserved. Two component tests and Ruff passed. Source/protocol890ca08c8; namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c053-geographic-admission-v1`; result SHA256 `e1a524ea3dfb3565d4dd55e26cd6331b69db68fc9615f9bc6b784bfd6a193967`.
