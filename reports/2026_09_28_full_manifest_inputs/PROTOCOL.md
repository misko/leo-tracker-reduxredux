# Full-manifest scientific input expansion

Freeze all published DS7(88), DS8(65), DS9(105) manifest captures, sorted by
capture start and session ID. No outcome, cache-availability or geography
filtering. Reuse the complete DS7 full88 requests and combined30 inputs after
hash checks; prefer already archived combined30 paths. Archive remaining local
cache banks byte-for-byte. Export only missing cached observation/candidate
inputs through the unchanged read-only scientific ports. No waveform/IQ reads,
RF collection, provider fetch, production-service modification or QNAP writes.

Use unchanged corrected-DS6 causal five-anchor/top8-union banks, partition
seed2026092711, and existing loader eligibility gates. Verify capture/dataset
manifest bindings, pose hashes, sample rates, provider snapshots earlier than
capture minus505s, and DS9 minted GLRT bindings. Every capture stays in the
ledger, including failed/pending captures and track eligibility exclusions.
Do not describe any dataset as ready until every manifest recording validates.

Run a single scientific worker, BLAS1/nice19, address space4GiB. Caps:
observation export60s, banks240s, validation30s. Reused inputs may be validated
in a single bounded1800s invocation. Missing inputs are processed in fixed
chronological five-record batches, each invocation bounded1800s. Preserve every
attempt and exit code; no automatic scientific retries.

Before starting each stage, require Linux MemAvailable of at least1GiB for
validation, 1.5GiB for observations, 2GiB for banks. Earlier measured peak RSS
was respectively160132/405916/891688KiB. If headroom or invocation time is
insufficient, leave the stage pending without launching it. A later explicit
invocation may continue an unstarted stage; failed stages must remain failed
unless a separately documented repair/retry is approved by the research plan.

Archive runtime versions and installed reader source snapshots. Hash inputs
and outputs of every executed stage. Complete full-dataset fits are a separate
experiment after scientific input readiness and sufficient memory are verified.
