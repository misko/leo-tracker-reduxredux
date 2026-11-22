# Timing and signed carrier interpolation between full visits

Using the full scout on alternating visits per RF yielded usable two-sided proposals on **11 of 102 bracketed physical lanes**. Those proposals covered **12 of 72** exported middle factors and **2 of 22** second-scan factors. Only **eight lanes** had proposals for every exported factor, even with an allowance for the final verifier to move the estimate. The full receiver calls on those eight lanes cost **5.1%** of the measured native CPU. Signed refinement, cancellation and independent discovery would consume part of that budget. The audit stops here because the supported visits give too little opportunity to replace the scouts. [Receipt with factor tuples and predicted timing and CFO](receiver-brackets-results.json)

## Fixed schedule and proposal

The first, third and subsequent odd-numbered eligible visits of an RF lane are anchors. The eligible visits between them can use both surrounding independently measured anchors. The lane key separates recording, stream generation, physical receiver, pilot edge, tuned RF and nominal channel. Missing lookahead at the end uses the full detector. The candidate needs a nonempty, unique one-to-one pairing of all anchor factors. Empty anchors, unequal factor counts, ambiguous associations, implausible links and excessive gaps require the full detector. A pairing never uses factors on the other antenna.

Each side of the middle visit is at most two seconds from its anchor. The link bounds are inherited from the causal experiment, with at most 8,000 Hz/s of signed carrier change and 1,000 native samples per second of unwrapped absolute frame-phase drift. Absolute phase uses the hardware sample counter and the 40,000-thirds-of-a-sample frame period. Each resulting link interpolates signed CFO and wrapped frame phase using elapsed hardware samples. Proposal generation sees only those anchors and the middle hardware counter and signed search band. The offline oracle compares its result with the middle waveform's exact `950c2b94` factor set. [Past-only experiment and inherited bounds](receiver-tracking.md) · [Frozen verifier](receiver-stencil.md)

A forecast on the previous physical experiment had to refine within four samples and 1,250 Hz. The audit records that nominal radius and the earlier forecast confirmation envelope of five samples and 1,600 Hz. The outer comparison grants six samples and 2,250 Hz by allowing the existing final verifier to move an estimate by two samples and 1,000 Hz. This is a permissive enclosure for the existing narrow route. Matching one anchor to one factor takes no account of which candidate would win a real signed refinement. All report counts therefore measure proposal coverage, with the full detector as the reference.

## Physical and geographic coverage

| Existing slice | Total lanes | Bracketed lanes | Proposals | Bracketed factors covered, outer allowance | Bracketed residuals covered, outer allowance | All factors covered in lane |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0016 physical, first 128 scheduled visits | 232 | 102 | 11 | 12 / 72 | 2 / 22 | 8 |
| Public northern simulation, first 40 visits | 80 | 32 | 4 | 4 / 8 | 0 / 0 | 4 |
| Public southern simulation, first 40 visits | 80 | 32 | 4 | 2 / 4 | 0 / 0 | 2 |

The physical slice had 116 eligible visits. Before any middle-window computation, 91 of 102 bracketed lanes would need full detection. Fifty had unequal anchor counts, 27 had no factors at either anchor, and 14 had no compatible signed pairing. Forty of these fallback lanes contained confirmed middle factors. Twelve additional lanes had no later anchor within the prefix. Each public simulation had no residuals in the scheduled middle lanes, so it exercises primary coverage only. Both had two nominally compatible full-lane proposals. Public simulations are geographic development checks.

The surrounding measurements did not predict every observed carrier. Fifteen physical middle factors, ten from the second scan, had no allowed slope link to either anchor. The lane at visit 89 on antenna 0 had a compatible −236.077 kHz primary, plus a gated −80.793 kHz residual absent from both anchors. Testing only the proposed primary could therefore miss an independently verified weaker carrier. At visit 91 on antenna 1 both anchors and the middle visit had two factors, yet one predicted carrier was absent from the middle result and one middle residual was absent from the proposals. At visit 44 on antenna 1 the anchors agreed on a carrier and the full detector found no middle factor. A middle-window detector would still need independent signed confirmation, a full fallback after failed confirmation and a discovery path when confirmation succeeds.

The physical CPU fraction on all proposed lanes was **6.8%**, with **5.1%** on the eight compatible lanes. These fractions include the entire original detection and verification cost. The corresponding full-call fractions were 8.8% and 8.8% on the northern simulation and 10.9% and 5.4% on the southern simulation. The physical predictions required about 0.354–0.355 seconds of lookahead. Both simulated prefixes required two seconds. The study measured two-sided information availability and its CPU ceiling. It did not time a substitute detector or use its forecasts for publication.

## Reproduce

The audit uses existing chronological, integrity-checked I/Q. The pilot and RF rules were fixed before opening those prefixes. Both receivers, all valid visits and both signed scans use the exact frozen packed verifier. Two component tests cover crossing the frame wrap with large counters, signed interpolation with reversed factor order, ambiguous links, changed anchor counts and a transient second carrier.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_audit=tools.pipeline_eval.variants.experimental.receiver_brackets
algo08_assets=/opt/leo-algo08/current/assets

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python -m "$algo08_audit" \
  "$algo08_work/receiver-stencil.so" \
  --physical-binding /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json \
  --assets "$algo08_assets"
algo08_lock "$algo08_python" -m "$algo08_audit" "$algo08_work/receiver-stencil.so" \
  --simulated-panel /tmp/leo-regional-qZJKBw4W/public/panel.json --assets "$algo08_assets"
algo08_lock "$algo08_python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_brackets.py
```
