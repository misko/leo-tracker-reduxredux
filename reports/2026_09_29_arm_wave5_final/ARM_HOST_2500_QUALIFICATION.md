# ARM versus host 2.5 MS/s qualification

The 152 saved 2.5 MS/s contexts emit the same 6,030 candidates on host and
physical ARM. Candidate objects are not bitwise identical: 1,783 of 3,344
receiver/windows contain at least one floating-point field difference.

The largest observed absolute differences are 9.03e-8 for coarse score,
4.44e-16 for exact score and margin, 3.47e-17 for control score, and
6.94e-18 for conditioned score. Epochs, bins, CFOs, candidate inventory, and
other fields match in the corresponding candidate order.

Frozen matching against original DS7 references finds 4,506 matched hits on
both sides, with zero ARM losses and zero gains. This qualifies hit identity
and inventory parity for the physical 2.5 MS/s panel; it does not claim
bitwise cross-architecture equality.

Machine-readable hashes, field counts, and matcher provenance are in
`arm-host-qualification.json`.
