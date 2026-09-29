# Wave5 combined candidate

This composes the sealed 0.312 per-rate gate and quadratic degree-two,
block-64 conditioned screen with raw stride-aware CI16 ingestion.  Final GLRT
remains FP64.  Host and sanitizer retain the gate, final-reuse, fine-budget,
conditioned-bound, and direct-ingest units.

Exact host parity is complete against gate-quadratic: 86,439 candidate objects
over 704 DS7 dwells, 3,624 over 32 DS8 dwells, and 3,689 over 32 DS9 dwells,
with zero changed candidates or windows in every cohort.  The ARM build is
cross-compiled; target execution and timing are root-owned.

ARM fused SHA-256:
`979be6134f862eb92d3491d6e9e512479510fc2fc5ee06bfd1b34a229233047b`.
ARM receipt SHA-256:
`a66cdd485cd5875f0bb891beba57cf438c76b29a8a82aa9c9617041f863621d4`.
