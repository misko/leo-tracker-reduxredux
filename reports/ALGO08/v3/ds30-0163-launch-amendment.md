# DS30-0163 launch order amendment

The first candidate attempt exited during isolated Python import in
**0.053210 wall / 0.051837 CPU s**, before opening a solver job.
The assigned installed command then completed in **20.766805 wall /
20.745002 CPU s**. Its products and the failed candidate log are
frozen together at
`12b00b10289013a825d5a9c2eb35e2adc81931d7d16b047c15cb22ea335673ab`.
The reference and outcomes remain unopened for scoring.

The launcher now defers imports that need the repository's local
`leo` package during admission and scoring. The isolated child
can enter the existing installed bootstrap with those imports still
unloaded. Its import-only smoke on the real `python -IB` entry
verified both worker callbacks and confirmed no early `leo` load.
This changes no science source, compiled library or scientific
settings. The finalized telemetry correction remains pinned.

Run exactly one newly measured candidate and reuse the original
installed publication. The **actual measured order is installed
first, candidate second**. Retain the failed-start and prior warm
admission costs separately. The order-deviating pair provides
blind science and measured clocks, with no standalone claim that
it passes a speed gate. [Scientific protocol](ds30-0163-combined-protocol.md)
