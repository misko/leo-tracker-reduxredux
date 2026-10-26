# The fixed four existing-data inputs are prepared

All four original members completed the existing stored-GLRT preparation once,
with no replacement, retry, timeout or input failure. The unchanged sample is
[sample.json](../prepared/sample.json), SHA256
`c19af75560ff1ff962ec73064c49b68d10fe94bd990b37b09f73e588242e8ec5`.
The earlier metadata-only hold remains documented in the initial findings and
`prepared/STATUS.md`; this receipt records the subsequently authorized resume.

| Case | Original GLRT winners | Complete graph owners | Curved owners | Causal regional candidates | Charged preparation seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| LATER4-0001 | 4315 | 140 | 75 | 1342 | 15.999 |
| LATER4-0002 | 4892 | 131 | 87 | 1434 | 16.240 |
| LATER4-0003 | 2996 | 101 | 53 | 1388 | 14.479 |
| LATER4-0004 | 3964 | 110 | 67 | 1518 | 15.225 |

These counts describe available input and curve extraction, not satellite
identity, accepted position-likelihood membership, measured position information
or localization accuracy. There is no new c-arm comparison at this preparation
stage; both arms must later use the same prepared input.

The existing `tools/prepare_algo02_ds23.py --stage all` exported the exact frozen
tracking bytes and constructed observations, the graph, radio-only nominal noise,
a causal regional current/previous TLE bank, the genuine earlier-epoch prior,
and 72-hour causal phase history/forecast. It did not perform discovery/retained
baseline inference, CFO refinement or localization. Each case's
`preparation_receipt.json` binds the actual prepared files.

The public fast-winner adapter reconstructed the original acquisition clock
bracket. Its midpoint and BEFORE-bound causal cutoff agree exactly with every
frozen sample member; filename and manifest-creation time were not substituted.
Both current and historical TLE inputs are restricted by the original causal
cutoff. No new raw-data query, IQ payload read, detector call, position fit or
GPS read occurred. Evaluation-site authority subsequently supplied by the user
was kept out of these inference inputs; earlier metadata alone did not establish
that site.

Execution used two single-BLAS workers. An external supervisor capped each
entire export/preparation process group at 140 seconds, covering legacy child
processes. Tool session `34065` exited zero; supervisor PID was `972013`.
Wall time was **31.466531 seconds**. Cumulative charged worker time was
**76.776633 seconds**, including 13.850416 seconds of earlier metadata checks
and 0.983401 seconds of freeze/fixtures, below the original 600-second cap.

Six owned fixtures passed. The first fixture run caught a wrong wrapper key
(`clock_authority` instead of the existing `capture_time_authority`); its failed
receipt is retained and its time is charged. The source fix changed no sample,
clock definition, scientific preparation rule or previously frozen study.
Independent preflight checked all 737 source/input bindings before root GO.

The terminal [execution ledger](../prepared/preparation_execution.json) retains
all four statuses and process records. Its SHA256 is
`8398154dca801ed0f830fd477d251cb18d80ff7980372daf2a263a8fd642bc31`.
The [preparation RF seal](../prepared/preparation_RF_seal.json), SHA256
`ebdc1a80ba493776f974e2e9bf17f73c9c3ba2cdc6aa4392c1812d44dbd08886`,
binds the unchanged sample and all terminal prepared outputs. The preparation
protocol is [preparation_protocol.json](preparation_protocol.json), SHA256
`189c1cbfb11c862666a1c2912e3c75f233a387525177224f38195e6a296825d0`.

The next inference producer must still run the full retained baseline lineage;
these files are not fitted parents or final associations. Historical detector
runtime compatibility and exact replay parity remain separate prerequisites
before any future measurement correction. These are additional already-recorded
cases with incompletely audited prior exposure, not a pristine holdout.
