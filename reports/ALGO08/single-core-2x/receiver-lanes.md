# Simultaneous antennas and the receiver CPU floor

The current receiver's two antennas share too few verified timing proposals for one lane to authorize the other. On 80 saved dual-I/Q visits, only **56 of 141** verified factors had a distinct partner phase within two samples. That count stayed at 56 with an eight-sample tolerance and fell to zero when the signed CFO also had to agree within 1 kHz. **37 of 55** second-scan factors had no partner phase within two samples. The experiment kept both acquisitions and their independent measurements. [Paired waveform audit](receiver-lanes-results.json)

The historical partner-local receiver searched the second antenna using only the first antenna's reported phases. It cut median partner CPU from 12.01 to 3.45 ms but recovered 17 of 49 original partner signals. The other 32 lacked a nearby primary phase. Matched phases could have large carrier offsets between the independent receiver chains, so that implementation measured the partner carrier directly. In an earlier exact ingress comparison, taking one strided antenna directly from CI16 saved only 0.12 ms median CPU over making a packed one-antenna copy. [Historical partner-local report](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_19_receiver_screening/antenna-confirmation/partner-local/README.md) · [Historical strided-input report](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_19_receiver_screening/pilot-influence/one-lane-arm/README.md)

## Current paired waveform evidence

The audit runs the same frozen receiver on each physical channel of each archived stereo visit. It finds the largest distinct matching set at each tolerance and measures the two directions separately. Only verified donor outputs can nominate phases. It does not measure what all of a donor's rejected or unresolved scout peaks might have supported.

| Evidence in target lane | RX0 donates to RX1 | RX1 donates to RX0 |
| --- | ---: | ---: |
| Verified target factors | 55 | 86 |
| Verified target factors when donor has no factor | 5 | 27 |
| Distinct donor pairs within two wrapped samples | 28 | 28 |
| Distinct donor pairs within eight wrapped samples | 28 | 28 |
| Distinct pairs within two samples and 1 kHz signed CFO | 0 | 0 |
| Positive target lanes whose entire set had a distinct donor phase within two samples | 14/37 | 8/49 |
| Target second-scan factors with no donor phase within two samples | 10/18 | 27/37 |

## Cost of sharing work while keeping both antennas

The frozen receiver already reuses the same asset, static lag filters and FFT plans for both lanes. Signal-dependent arrays, candidate ranks, amplitude fits, residuals, and GLRT evidence remain independent. Dispatch and the receiver adapter above native calls cost 3.3–4.5 ms for an entire short sealed prefix. The table uses the 1.317-second native profile, assumes equal antenna costs, and removes the listed work for one antenna without charge. Batched FFT execution and a common sample pass might achieve part of this savings while still computing both signals. [Frozen receiver stage profile](receiver.md) · [Complete acquisition profile](receiver-ingress.md)

| Work removed in the optimistic arithmetic | Native CPU removed | Native speedup ceiling under this arithmetic |
| --- | ---: | ---: |
| Timing and carrier transforms on one antenna | 11.0% | 1.12× |
| Also remove one antenna's input conversion, FIR and verifier load | 19.7% | 1.25× |
| Remove the independent frame confirmation stage altogether on both lanes | 3.6% | 1.04× |

The upper-edge DS30-0374 prefix spent 0.203 s on 58 native calls. Extending that measured mean to its 9,288 full-recording lane calls estimates about 33 s of detector CPU. That extrapolation assumes a similar mix of first and second scans throughout. Saving another 14–20 s would require removing roughly 43–61% of this native cost. Even the generous 19.7% paired-work calculation projects about 6.4 s. This is too small to justify a paired implementation as the main route to the remaining publication budget. [Measured full publication](measurements/DS30-0374.json)

The largest structural opening is the lane-independent redesign of the first and residual timing and carrier searches. One candidate is a linear bank of pilot projections per physical lane that can reuse the first scan's scores after cancellation. Each residual score would subtract that lane's fitted pilot contribution, with a conservative bound for quantization and any uncomputed blocks. A credible escalation rule needs to prove that omitted timing and signed-frequency regions cannot contain a competing proposal, including weak or close second carriers. Ties, possible clipped samples, or loose bounds would use the complete released search. The present frame normalization and principal-mode selection are nonlinear, so their surfaces cannot be updated this way. The linear bank would be a new acquisition algorithm and requires independent factor and downstream qualification. The measured confirmation gate alone is too small a cost to motivate staged accumulation there.

## Reproduce

```bash
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  -m tools.pipeline_eval.variants.experimental.receiver_pair_audit \
  /tmp/leo-algo08v2-2x-bench/receiver-final-candidate.so \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  --assets /opt/leo-algo08/current/assets
```

Two audit tests passed. They verify wrapped phase, signed CFO, one-to-one matching, and explicit counting of donor-empty and second-scan evidence.
