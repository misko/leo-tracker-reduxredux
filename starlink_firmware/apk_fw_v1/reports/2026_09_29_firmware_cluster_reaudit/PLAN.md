# Fresh firmware-to-clustering investigation

The user explicitly resumed with a revised active objective. Old blocked-audit
counts do not carry forward. Use existing DS7/DS8/DS9/DS10, existing firmware,
and public literature only. No new RF, fixture changes, or unrelated edits.

1. Inventory saved hierarchies and association artifacts, preserving source hashes,
   sample scope, metrics and known-pilot/T-code contamination. Do not treat word
   distributions, waveform profiles and individual symbol groups as equivalent.
2. Independently parse ELF load segments, entry points and byte order; re-disassemble
   relevant routines directly from mapped binary bytes. Audit software packing,
   receive descriptors, initialization, PHY registers, coding tables, sequence
   handling and hardware variants. Prior reports locate code, not prove conclusions.
3. Build an association-to-firmware evidence ledger. Rank proposed meanings by
   reachability and RF mapping evidence, not diagnostic names alone. Distinguish
   structural invariants from speculative semantic interpretations.
4. Freeze focused falsifiable tests before inspecting their results. Fit on
   discovery observations and evaluate held-out observations, preserving sessions,
   receivers, sample-rate support and time where required. Account for searches
   across features/groups. No blind scan without a fresh independent constraint.
5. Produce a standalone report with raw-code evidence, every inventoried association,
   negative findings, sensitivity checks, reproducible scripts/tests and figures.

Initial priorities: (a) firmware claims that could incorrectly label a dendrogram
as identity; (b) whether stable groups match field-width/state constraints after
removing known waveform families; (c) whether relations persist across receiver
and revisit boundaries rather than within a single session. A software enum or
descriptor offset is not an RF bit position; SATAddr is not assumed to be NORAD.
