# Rank-only production review

The independent SOL review found no ordering or lifetime blocker in production
tracking source `eeefee63d956a1aeaeb88ee0b2f2560876107a9f5f79e3b5aa28616036d7b96c`.
The tuple owns its two double values and borrows only the candidate-ID string.
Candidate storage remains immutable and alive through each synchronous
comparison, including during parallel lane execution. The tuple retains the
same lexicographic comparison and numerical operations as the owning version.

The first review found that the existing real reconstruction fixture selected
its duplicate by weight, so it did not exercise an equal numerical rank. The
added `test_same_source_equal_numeric_rank_uses_lexical_candidate_id` in the
normal `test_tracking.cpp` supplies nine same-source pairs with identical
numerical fields, asserts the lexically smaller candidate at every selected
point, and verifies full result equality after reversing input order. The
reviewed test SHA-256 is
`d23cbecd99eda11160f25cc90d2c8955ee60658b4086796518fd5ea609ad3e32`.
This closes that test-coverage gap through the actual reconstruct path; the
separate comparator-only research test is supplementary evidence.

Earlier online/application archives embed the previous tracking implementation.
A deployment claiming this optimization must rebuild its numerical archives
and application coherently and qualify the resulting bytes. Existing cache
receipts remain historical evidence for their recorded source hashes.
