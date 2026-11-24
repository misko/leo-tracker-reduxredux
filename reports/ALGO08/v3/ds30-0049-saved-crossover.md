# DS30-0049 crossover isolates the regression to receiver observations

The **2.620 km fitted-`c` regression followed the receiver packet**. Both
solvers returned exactly the same terminal, positions, RF fit and ordered
owners when given the same packet. The change was **+2.646 km** with fixed
`c = 0` and **+2.620 km** with fitted `c` under either solver. Four complete
saved publications supply the comparison. Both saved diagonals exactly
reproduce the independently verified generation-2 raw controls.
[Frozen protocol](ds30-0049-saved-crossover-protocol.md) ·
[Machine receipt and ordered owner proof](measurements/ds30-0049-saved-crossover.json.gz) ·
[Original raw comparison](ds30-paired-evaluation.md)

| Saved detector packet | Solver | Fixed-zero horizontal error | Fitted-`c` horizontal error | RF RMS, zero / fitted | Ordered owners per arm | Saved child wall / CPU |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Installed ALGO08v3 | Installed ALGO08v3 | 1.826 km | 1.420 km | 129.663 / 129.671 Hz | 320 | 8.65 / 8.06 s |
| Installed ALGO08v3 | Charted successor | 1.826 km | 1.420 km | 129.663 / 129.671 Hz | 320 | 7.35 / 7.04 s |
| Charted successor | Installed ALGO08v3 | 4.472 km | 4.040 km | 168.634 / 168.814 Hz | 268 | 7.84 / 7.74 s |
| Charted successor | Charted successor | 4.472 km | 4.040 km | 168.634 / 168.814 Hz | 268 | 6.36 / 6.31 s |

The original controls shared **986 issued and 932 admitted visits**,
1,864 ordered RF opportunities, the signed inventory and anchor clock,
the original offer and the original causal TLE roster. The installed
packet contained 531 candidate factors and the successor contained 600.
The receiver change removed 71 owners, added 19 and kept 249 with the
same NORAD and role, independently in both calibration arms.

Of the 71 lost owners, **44 had no factor passing the successor's
fractional margin gate**. The other 27 lanes still had a passing
factor. Comparing their strongest passing rows gives a median absolute
shift of 38.010 kHz and 2,031.799 samples, with four exactly matching CFO
and epoch pairs. For the 249 retained owners the analogous medians
are 79.645 Hz and 0.344 samples, with 39 exact pairs. The lane join uses
the signed session, receiver and sample counter. A strongest-passing
row is a detector diagnostic and can differ from the factor finally
used by a solver. The deployed held selector chose `unfiltered` and
made zero refinement calls on this recording.

## Evidence and timing boundaries

The installed solver uses its actual released publisher and checked
lazy-startup facade. The successor reuses the charted early checks
and its exact positive solver, renderer and publication stack. The
saved adapter relaxes only the raw-only detector inequality after
authenticating the submitted packet. Both paths replace the ordinary
inventory and acquisition reads with the already-published exact
inventory and a single authenticated handoff. Neither reruns the
receiver nor reapplies the held selector to the saved packet.

The independent verifier opened every new positive product. It
required both finite calibration arms, all 179 grid locations,
the bound path and all eight PNGs. For each diagonal it also compared
the native and terminal hashes, both raw arms, official owner digests,
the entire grid apart from its elapsed clock, the path, and the
encoded and decoded RGBA digests of every raw PNG. All passed. The
installed ordered lists rederive the original raw owner digest
`sha256:69c2c5acc1769006ca971c2434b406347a79f573d02094bf180395f5e340a4db`
in both arms. The complete machine receipt preserves those rows and
their producing witness SHA.

The generation-2 original-file workers took **18.679 / 13.600 s**
installed/successor through common verification, including acquisition.
Their corresponding child-only clocks were **18.276 / 13.200 s**.
The saved clocks above include neither waveform ingestion nor the
separately run independent scorer. Their inputs were read in four
separate Gauss leases, with positive process input blocks and major
faults varying across launches. One installed setup attempt stopped
before inference at 1.83 s elapsed / 1.30 s CPU when the startup facade
was installed twice. The corrected launch reuses it once. The original
archive was reopened read-only and its body reads were authenticated by
the production catalogue reader. The original recording and waveform
paths were denied. No new scan or new raw-worker trial ran.

## Priorities for the 2× target

1. Recover observed detector support and ambiguous time/frequency
   candidates before ranking. The largest directly documented
   loss is 44 owner lanes with no passing successor factor. Refining
   CFO only on surviving positives cannot restore those lanes.
   A full-aperture recovery policy should therefore measure both
   accepted support and alternative timing/CFO on signed, paired
   opportunities. Both calibration arms and this counterexample
   should remain separate acceptance checks.
2. Retain the charted solver on equivalent observations and measure
   receiver-side speedups with full-aperture support held fixed.
   The successor's raw acquisition took **6.046 s** on this case,
   compared with **3.983 s** to solve and **1.203 s** to render.
   Against the observed **9.340 s** half-time budget, the current
   verified successor is **4.260 s** over. Even granting the entire
   solve clock for free would leave about **9.617 s**. More solver
   approximation has no demonstrated accuracy benefit on this case.

The crossover qualifies only DS30-0049 and provides no full-pipeline
timing for a hybrid receiver. It changes neither the batch nor its
frozen candidate. Five component tests passed. To reproduce, run
`ds30_0049_saved_crossover.py` under released Python `-IB` with a new
output root per cell. Run the two diagonal modes first and verify them
with `ds30_0049_saved_crossover_score.py` before the two cross modes in
the frozen order. Read-only verification uses the checkout's normal
standard store. Use `--full` to join the sealed survey and save the
scientific comparison after all four publications.
[Measured entry](ds30_0049_saved_crossover.py) ·
[Scorer](ds30_0049_saved_crossover_score.py) ·
[Tests](../../../tests/pipeline_eval/test_ds30_0049_saved_crossover.py)
