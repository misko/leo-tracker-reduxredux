# Counter/UTC timing integration

New firmware-adaptive archives can carry `evidence.counter_utc_timing` in
addition to their historical start bracket. The importer binds the new raw
evidence to session, generation and radio identity, evaluates its declared
uncertainty and seals a `CounterUtcTimingV4` into a new IQ manifest major 6.
Existing timing and IQ manifest versions are unchanged.

Recording readers require no radio/PPU imports. They verify the raw-evidence
digest and replay the qualified nominal origin and full-span drift bound.
Unqualified records retain an explicitly approximate display timestamp; they
cannot enter TLE matching through the temporary legacy two-second policy.

For qualified counter timing, the matcher evaluates shared UTC shifts with
spacing no larger than 25 ms across the recorded error envelope. Observation
IDs and training/held-out partition are fixed across the grid. Catalogue,
orbital tau and CFO-offset fits remain training-only; each grid point preserves
the existing held-out, polynomial-null and +/-500-second diagnostics. A changed
leader, failed held-out persistence or abstention at any point adds an explicit
UTC-sensitivity abstention reason. No UTC offset is selected using held-out
scores. Orbital tau remains separate from UTC error.

This is a finite-grid diagnostic, not proof that candidate identity is stable
at every continuous offset. Existing candidate-only/no-identity semantics stay
in force. Up to nine matcher runs per physical group are needed for a +/-100 ms
envelope, so production wall-time impact must be measured before deployment.

The PPU dependency is pinned to the matching counter-evidence implementation.
The source changes have synthetic and regression validation, not live RF
qualification. Hardware calibration is boot-bound and defaults to absent;
unknown snapshot age, oscillator tolerance or host UTC bounds cannot qualify.
Firmware issue: https://github.com/misko/plutosdr-fw/issues/107.
