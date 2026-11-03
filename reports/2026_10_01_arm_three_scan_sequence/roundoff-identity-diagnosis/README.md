# Floating fit summaries affect positioning partitions

The independent x86 native pipeline starts from original baseline IQ and uses
the same frozen detector algorithm. Its CFOs and passing decisions match the
prior physical ARM queue-32 run exactly; GLRT margins differ by at most
4.44e-16. All 80 ordered track memberships and alias assignments match.

Nevertheless, the full position search differs: the selected coordinate remains
the same, but its score changes by 4.6282586633 Hz and the search trace diverges.
This is distinct from the same-checkpoint module tests, which pass.

The cause is the private checkpoint adapter in
`native/adaptive/pipeline/track_input.cpp`: `material` includes the complete
serialized `TRACK` line, including fitted rate/intercept, residuals and weighted
support. It hashes that material into the track identity. The location adapter
then incorporates that identity into observation identities, support digests,
partition seeds and training masks. Tiny floating arithmetic differences can
therefore change the held-out experiment despite identical memberships.

The diagnostic changes only 77 floating `TRACK` summary rows in the x86 output
to the corresponding historical ARM summaries; every `POINT` row, measured
observation, support row and membership is untouched. All 400 search coordinates
then agree, the selected score agrees exactly, and maximum score difference is
3.99e-11 Hz (within the predeclared 1e-9 Hz control tolerance). See `receipt.json`
for the command and comparison. Original outputs remain unchanged.

This diagnostic is not substituted for the real replay. A future fix should
introduce an explicitly versioned membership-based identity/partition policy
whose material excludes derived floating fit summaries. Published identities
must not be silently changed. The current ARM sequence deliberately retains the
frozen implementation so its measured behavior and limitations remain auditable.
