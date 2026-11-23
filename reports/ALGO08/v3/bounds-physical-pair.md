# ALGO08v3 bounds pair on DS30-0008

The three selected changes preserved the complete scientific publication and took 5.65 s longer elapsed and 2.29 s more CPU than installed ALGO08v3 in one physical pair. The candidate ran first with 0.95% of the input cached. The installed arm ran second with 76.75% cached. That difference limits attribution of elapsed time to the algorithms. [Measured pair](measurements/bounds-DS30-0008-pair.json)

## How much work could the three changes remove?

| Selected change | Dense DS30-0008 ceiling | What the saved tests measured |
|---|---|---|
| Stop refining a losing receiver hypothesis early | A free oracle that knew every losing hypothesis could save an estimated 2.5 CPU s. The tighter feasible bound priced at 1.19 CPU s before paying for the check. | The implemented check reduced native receiver CPU by 2.0% on weak lanes and 2.6% on dense lanes, preserving the selected factors. [Receiver study](refine-bound.md) |
| Reuse the fixed part of the position solver's matrices | Repeated setup cost 1.045 CPU s. Copying and validation leave roughly 0.77 CPU s available. | Fixed constructions fell from 228 to 14 on dense and 94 to 9 in a southern simulation. All robust likelihood updates were still necessary. [Matrix reuse study](incremental-layout.md) |
| Reject impossible satellite matches using the offered region | The entire dense fine-recovery stage cost 5.03 CPU s. Earlier ranking can use weak matches, so a regional exclusion there cannot guarantee identical results. | The check skipped 8,699 of 40,189 dense recovery trials. Recovery elapsed fell by 0.12 s. The northern omitted-region control kept its withholding decision. [Regional study](../single-core-2x/regional-doppler-envelope.md) |

These estimates describe different scopes and include work the implementations still have to do. The full combination below provides the direct end-to-end test.

| Measurement | Installed ALGO08v3 | Bounds candidate |
|---|---:|---:|
| Launch to sealed detections | 69.514 s | 79.919 s |
| Detections to terminal | 58.425 s | 54.250 s |
| Terminal to exit | 21.947 s | 21.370 s |
| Total elapsed | 149.886 s | 155.539 s |
| CPU | 109.103 s | 111.393 s |
| Input blocks | 3,727,504 | 15,866,592 |
| Compressed input pages resident | 1,533,163 of 1,997,612 | 18,908 of 1,997,612 |

The measured speed ratios were 0.964× elapsed and 0.979× CPU. The shorter detection-to-terminal interval is an elapsed observation within this single pair. The candidate reused 214 of 228 fixed layouts in the measured constructor scope and excluded 8,699 of 40,189 fine-salvage supports across 1,047 trajectories. [Timing and activation counters](measurements/bounds-DS30-0008-pair.json)

## Evidence

Both runs produced 13,530 identical ordered probes and 7,016 identical ordered selections. The shared raw authority, input manifest, scan report, calibration arms, owners, scientific path and grid digests, and all eight PNG byte and decoded RGBA digests matched. The fresh installed run also matched the archived ALGO08v3 witness. [Equality checks](measurements/bounds-DS30-0008-pair.json)

The native run ID changed from `blind-compact-bf1e17f50683feaa42b84082dc2f8d08` to `blind-compact-3b1cd9ad25d2fe42103c1753def713b8`. Both launchers published `algo08-v2-2a35248362339057a6a8486b1006c0e2`. The native detector digest and the analysis digest and ID it determines account for the change in detection bytes. The terminal and publication manifest changed in their derived bindings. Their other fields matched. [Fingerprints and document checks](measurements/bounds-DS30-0008-pair.json)

With matched observations, candidates, other priors and budgets, both builds gave these calibration results. The position error uses the existing radio/time-eligible operator site authority. [Calibration ablation receipt](measurements/bounds-DS30-0008-pair.json) · [Reference audit](../../2026_11_21_ds30_full/reference-audit.json)

| Quantity | `c = 0` | Fitted `c` | Fitted minus zero |
|---|---:|---:|---:|
| RF RMS | 129.703040 Hz | 129.662931 Hz | −0.040109 Hz |
| Horizontal error | 1.638978 km | 1.511956 km | −0.127022 km |

## Inputs and build

DS30-0008 is a dense development recording. Both arms used its 14 sealed segment manifests, signed waveform authority, 25 km offer and causal TLE archive. The candidate used the selected PGO carrier-refinement bound, fixed likelihood-layout reuse and the hard support bound inside fine salvage. The launchers kept the original advisory read hints, orbit retry policy and publication pipeline.

The installed launcher verified the candidate’s private payload with its ordinary checks. The staged payload copied the digest-pinned installed payload and replaced `receiver.so`, `detector_sha256` and `sources["receiver.so"]`. The original and measured payload SHA-256 fingerprints were `6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f` and `52562c4e96a53270c244971c90740eae14240c2ce8179febf217abfe94d4cf5c`. The selected receiver, derived specification, three solver source files and launch scripts are archived under `/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0008-build`. The selected native receiver SHA-256 was `7ac6de98302ce65c52fdad2f630094e14ab4c503999ba9f3695be2c4403a51b1`. [Build inventory and hashes](measurements/bounds-DS30-0008-build.json) · [Payload staging script](prepare_bounds_payload.py)

## Reproduce on Gauss

The timed pair used one uninterrupted exclusive Gauss lock on CPU 2 under the `leo` account at nice 15, best-effort I/O priority 7 and one numerical thread. The candidate ran first. Both arms started with empty publication directories and shared a Matplotlib font cache prepared outside the clocks. Linux counted resident pages immediately before each launch. The operating system managed the recording cache throughout.

Use the measured source checkout and the archived native receiver. The preparation command verifies the original install and the derived payload. The driver verifies both launchers, the signed assignment and the archived installed publication before timing.

```sh
repo=/var/tmp/leo-algo08v3-bound-pair
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
results=/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac
out="$results/v3-bounds-DS30-0008-reproduction"

if [ ! -e /var/tmp/leo-algo08v3-bounds-physical-payload ]; then
  "$release/venv/bin/python" "$repo/reports/ALGO08/v3/prepare_bounds_payload.py" \
    "$results/v3-bounds-DS30-0008-build/receiver.so"
fi

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/env PYTHONPATH="$repo/src:$repo:$release/src:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -Bs "$repo/reports/ALGO08/v3/triage_bounds.py" \
  "$out" --first bounds
```
