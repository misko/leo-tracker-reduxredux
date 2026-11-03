# Local shortlist coverage is strong; mixture normalization still matters

The 378-setting probe finds no omitted leading candidate within the sampled
local region, but does find omissions at 100 km offsets. It also identifies
a separate issue: nearly complete retained likelihood mass does not preserve
signal/background odds when the signal mixture is renormalized over a much
smaller retained candidate set.

| Region | Settings | Minimum training signal mass retained | Training best omitted | Minimum full signal mass retained | Full best omitted |
|---|---:|---:|---:|---:|---:|
| N24 fitted locations | 27 | 99.999863% | 0 | >99.99999999% | 0 |
| Configured center | 27 | 99.999890% | 0 | >99.99999999% | 0 |
| Four ±12 km corners | 108 | 94.673240% | 0 | 99.995077% | 0 |
| Four 6 km interior offsets | 108 | 99.987212% | 0 | >99.9999999% | 0 |
| Four 100 km outer offsets | 108 | 7.03e−19% | 7 | 3.79e−32% | 7 |

Each setting is one of nine tracks at one observer location and timing offset,
not an independent track or trial. The local results cover 270 settings, the
outer stress test 108. Only one local setting falls below 99% training mass:
a DS8 track at E=+12 km, N=−12 km, time=−5 s. Its complete-track retained mass
is 99.995077%. Complete-track evidence is not used to select the shortlist.

## Normalization effect despite complete retained mass

Let R be retained visible candidates, V the full visible catalogue, and m the
fraction of full candidate likelihood sum in R. With uniform candidate priors:

```
retained signal likelihood / full signal likelihood = m × |V| / |R|
```

When m is nearly one, the two normalized signal likelihoods can still differ
by tens of times. Holding the same 0.8 signal / 0.2 background prior fixed
changes the resulting signal/background odds by this factor. Neither model's
probability is automatically a calibrated physical confidence; the change is
a model-definition difference that requires explicit treatment.

The largest complete-track local responsibility change occurs on a DS9 track
at E=−12 km, N=−12 km, time=0: the candidate likelihood mass is effectively
fully retained, but the signal probability is **0.8774** when normalized over
14 retained-visible candidates and **0.1600** when normalized over all 526
visible candidates. The omitted mass has log probability −164.09, so missing
signal numerator mass cannot explain this difference.

That is a corner-of-domain example, not the fitted operating point or a
posterior-weighted result. At fitted locations including ±5 s timing, the
maximum training/full responsibility differences are 0.4722/0.3002. At the
fitted locations with zero timing, the preceding nine-track probe found both
probabilities nearly one. These pointwise changes do not establish that
normalization causes the geographic errors or that changing it improves fits.

The direct odds-ratio identity is checked on nonsaturated probabilities in
[odds-audit.json](odds-audit.json). This distinguishes candidate-mass coverage
from signal-mixture normalization; a bank can pass the former while materially
changing the latter.

## Implication for the next prototype

A bounded next test should retain full-catalogue candidate prior mass rather
than automatically renormalizing it over the shortlist, while auditing the
omitted numerator contribution. Compare location and outside-scan prediction
before promoting any change. Merely increasing the unassociated-background
fraction without accounting for the changing candidate count would confound
this specific hypothesis with arbitrary prior tuning.

The finite local grid supports continued use of these shortlists as a local
numerical approximation for the sampled tracks. It does not establish global
search coverage: at the outer offsets, both training and full likelihood can
prefer candidates absent from the local bank. A broader search requires a
different candidate-support strategy or direct catalogue evaluation.

## Frozen design and verification

Use the same nine ID-selected tracks as the [initial full-catalogue probe](../2026_09_29_full_catalogue_probe/README.md).
Observer positions comprise each dataset's N24 point, configured center,
four ±12 km corners, four cardinal 6 km interior points and four cardinal
100 km exterior points. Each is crossed with timing −5, 0 and +5 seconds.
No posterior, residual or reference error selects the tracks or settings.

The exact causal catalogue is reconstructed through read-only archive ports
from original provider snapshot digests. All objects are propagated at the
actual observation epochs. The original training-mask visibility rule and
current contrast likelihood are applied. Retained predictions and visibility
are checked against the original bank at every tested timing node. Omitted
mass is computed directly in log space, retaining tiny tails that would be
lost by subtracting retained mass from one.

All 378 bank replays are exact (zero Hz discrepancy), with identical retained
visibility masks. All three workers exit zero; summed runtime is 35.86 s,
maximum 13.96 s, below the 120-second cap. Source hashes, selected IDs, unique
settings and comparison populations are checked. Ruff passes. The
[summary](summary.json) reports each region/dataset and local timing slice;
raw outputs retain all cases and oracle source hashes. See [protocol](PROTOCOL.md)
and [full region table](TABLE.md).

No geographic fit or new RF collection occurred. Nine tracks and a finite
location/timing grid cannot establish catalogue completeness, calibrated
association probabilities, continuous-domain error bounds or sub-km accuracy.
Banks and the inherited geographic reference remain site-conditioned and
exposed; the reference is unsurveyed. No production or QNAP path changed.

```bash
python3 reports/2026_09_29_catalogue_domain/study.py prepare
python3 reports/2026_09_29_catalogue_domain/study.py batch
python3 reports/2026_09_29_catalogue_domain/summarize.py
python3 reports/2026_09_29_catalogue_domain/audit_odds.py
```

Outputs use exclusive creation; reproduce in a fresh archived-run context.
The pinned deployed interpreter is a research numerical oracle, not a new
production dependency. All report artifacts are local.
