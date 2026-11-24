# Same-face constraint signaling on saved publications

The paired active-face rule withheld the translated DS30-0086 false fix and preserved all 16 ordinary field outcomes. It also withheld a valid North simulation and retained three simulated false fixes. The evidence supports using a shared active face to identify some ambiguous constrained fits. It fails as a general gate for missing regions. [Frozen design](exact-face-constraint-protocol.md) · [Scored receipt](measurements/exact-face-constraint.json.gz)

## Exact coordinates and prior evidence

The rule withholds an otherwise complete fix if the final selected `c = 0` and fitted-`c` endpoints share an active face of the supplied square. It reads the unrounded local coordinates in the signed selected fit path. The existing bounds predicate permits one binary64 coordinate step inward from the face. The final sidecar, path and terminal are checked against the publication and enrolled offer. Survey references enter the later scoring pass. [Bounds predicate](../../../tools/pipeline_eval/variants/experimental/regional_bound_guard.py) · [Readout](../../../tools/pipeline_eval/variants/experimental/exact_face_constraint.py) · [Trial](exact_face_constraint_trial.py)

The earlier edge trial used either calibrated arm and a 32-representable-step geodetic conversion tolerance. Its named-v3 North +100 m fix already falsifies the stricter hypothesis. Both saved local endpoints hit the west face at exactly −12.5 km, with **106 / 141 m** horizontal error. The local exterior study used shared-single-face eligibility and additionally required a descent test. The prior sampled face-loss study applied a fixed **5.9915** loss gap and abstained if either arm found competitive face samples. [Earlier edge trial](../single-core-2x/edge-trial.md) · [Signed North endpoints](measurements/geographic-jackknife.json) · [Exterior descent](local-exterior-descent.md) · [Sampled face loss](grid-face-abstention.md)

## Previously released simulations

The 14 build-offer rows have seven containing and seven omitted offers. Site recordings recur across rows. The exact rule withheld **four of seven omissions and one of seven containing fixes**. The sampled face-loss rule withheld **six of six assessable omissions and five of seven containing fixes**. The named-v3 North −100 m receipt supplies the selected endpoints and full grid digest. The face-loss comparison for it is unavailable because the numerical grid rows could not be located among the saved publications. [Original simulated pairs](measurements/grid-face-abstention.json) · [North signed pair](geographic-jackknife.md) · [South 1 km pair](frozen-south-north-face.md)

| Saved build and offer pair | Containing / omitted clearance | Shared face rule, containing / omitted | Sampled face loss, containing / omitted |
|---|---:|---|---|
| Named-v3 North | +0.100 / −0.100 km | Withhold / withhold | Withhold / unavailable |
| Q15 North | +0.100 / −0.100 km | Retain / retain | Withhold / withhold |
| Named-survivor South | +0.100 / −0.100 km | Retain / retain | Withhold / withhold |
| Installed South, north face | +1.000 / −1.000 km | Retain / retain | Withhold / withhold |
| Integrated South, north face | +1.000 / −1.000 km | Retain / withhold | Withhold / withhold |
| Original regional v2 North | +5.797 / −1.500 km | Retain / withhold | Retain / withhold |
| Original regional v2 South | +5.891 / −1.500 km | Retain / withhold | Retain / withhold |

On South −100 m, both endpoints were **242 / 183 m** inside the east face, with **817 / 1,102 m** position errors and **6.502 / 6.392 Hz** RF RMS. The sampled-face gaps were **0.515 / 0.799**. On Q15 North −100 m, both endpoints were **41 / 110 m** inside the west face. Installed South −1 km put only `c = 0` on the north face, with fitted `c` **59 m** inside. Integrated South put both arms on that face. No independently saved North ±1 km pair with exact converged endpoints was found in the compared publications.

## Ordinary field and translated controls

The authenticated first sixteen ordinary successor outcomes were **14 complete, two withheld and zero failed** before and after either gate. Each calibration arm kept **8/16 within 1 km** and **12/16 within 2 km**. Neither gate removed a valid ordinary fix. The verified survey was 6.179 km inside the ordinary square for all sixteen. The closest returned endpoint to a face was 4.790 km inside. DS30-0452 uses the enrolled relocated attempt and proof. The frozen development receipt leaves **DS30-0105, DS30-0244 and DS30-0183** for a separately sealed prospective count. [Ordinary field provenance](ds30-centered-error.md) · [Per-case scored receipt](measurements/exact-face-constraint.json.gz)

| DS30-0086 offer | Survey clearance | Horizontal error, fixed / fitted | RF RMS, fixed / fitted | Face-loss gaps, fixed / fitted | Both gate outcomes |
|---|---:|---:|---:|---:|---|
| Ordinary | +6.179 km | 371 / 382 m | 179.824 / 180.081 Hz | 68.037 / 67.816 | Retain |
| Translated east | +5.204 km | 371 / 381 m | 179.824 / 180.081 Hz | 68.037 / 67.816 | Retain |
| Translated west | −5.204 km | 5,414 / 5,406 m | 170.109 / 170.330 Hz | 0.000 / 0.000 | Withhold |

Only the translated west offer has an authenticated half-width outward neighbor among the six shared-face triggers in the reviewed archives. The ordinary DS30-0086 offer moves the west offer centre **12.5 km east**, keeps the width and original sky-screen centre, and shares the frozen successor build, detector digest and causal archive. From the west offer's tested east face, the west fits have signed outward distances **0.000 / 0.000 km**. The ordinary fits lie **+5.438 / +5.434 km** outward. In the same local frame their northings move from **−7.815 / −7.789 km** to **−6.607 / −6.625 km**. The two South 1 km offers shift the centre by 2 km with a fixed sky screen. The North 100 m mirrors shift by 0.2 km and move the sky screen. The original regional v2 wider offers also move the sky screen. These controls cannot price a matched half-width retry. [Verified relative positions](measurements/exact-face-constraint.json.gz)

The exact ordinary second leg has an archived end-to-end clock of **51.71 CPU / 58.84 wall seconds**, covering raw launch and common publication verification. Its isolated saved-detector solve time was not recorded. The independently measured same-packet east and west saved-detector launches through publication took **16.25 / 30.74 CPU seconds** and **16.67 / 30.99 wall seconds**. Those clocks establish the scale of a full additional published solve. They do not measure incremental cost with in-process reuse.

The translated terminal, grid and path archive is `measurements/field-offer-translation-0086.json.gz` at revision `0bf5d531d844dc47ec4b2251de8c5b5a1b9d88b4`. This audit performed no new fits, orbit reads or waveform reads. It used no benchmark lease. Twelve component tests and nine face-loss regression tests passed. The prediction seal is recorded in the receipt. [Tests](../../../tests/pipeline_eval/test_exact_face_constraint.py)
