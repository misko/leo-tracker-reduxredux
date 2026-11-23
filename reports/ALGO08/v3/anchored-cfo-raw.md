# Guarded phase through the signed raw CLI

The guarded-phase CLI ran the original asynchronous acquisition path and sealed the same 56 selected factors as the existing exact fixed-epoch CFO CLI on one original signed DS30-0169 member. The two routes retained all 66 native factors, including ten rank-1 cancellation factors, in their original order and at the same native epoch and signed CFO. The maximum selected score change was **7.47×10⁻¹⁴** and the maximum refined CFO change was **5.83×10⁻¹⁰ Hz**. The stage ended at the verified detection packet. It did not run a solver or publish a position. [Staged packet comparison](measurements/anchored-cfo-stage.json.gz) · [Guarded verifier qualification](anchored-phase.md)

## Normal entry and identity

`anchored_cfo_raw.py --anchored-cfo-pack DIR` activates the approved guarded full verifier, the guarded 12 ms primary and the guarded fixed-epoch tail at the existing raw receiver boundary. The 20 ms anchor still uses the original native two-scan cancellation. The existing exact CLI and its recipe remain available with their original source and bits. The new wrapper uses the original schedule, full coverage, signed selection and fixed-epoch amend rule, including exact gathered fallback at the signed-band collar. It forwards the remaining options to the original named receiver-first bootstrap. Its patch scope covers the two native detector opens and the fixed-epoch refinement callback. Compressed read-ahead, decoded and compressed authentication, cutoff rules and the named publication options stay in the existing route. [CLI wrapper](anchored_cfo_raw.py) · [Original fixed-epoch CLI](short_cfo_raw.py)

The pack verifies five DSO digests, the source and benchmark pins, the block size, numerical guard definitions and its exact library versions before acquisition. The detector recipe incorporates the original mixed and fixed-epoch recipe, the reviewed phase pack specification and the guarded entry hash. The staged candidate recipe digest is `8d3ad4ed2f1391bd358400ca96c21998667dc820118d7a735a5bc513710f6d41`. The exact control digest is `701c05ac380d8c1b4b528ddbfd6925d1c13dd9b1832dbe2959f52c3177065d66`. The two sealed packets have a common raw acquisition authority and distinct detector identities. [Source, policy and binary recipe](anchored_cfo_raw.py) · [Canonical digests](measurements/anchored-cfo-stage.json.gz)

## One signed member through seal

The runner wraps the normal CLI only to bind the existing first member as a separately identified prefix inventory and stop at the post-acquisition `bind_native` port. The original segment manifest and chunk declaration still bind all input bytes. The released bounded source verifies its index, compressed payload, all **64** original decoded I/Q hashes and the complete decoded member before sealing. The prefix issued 64 and admitted 51 stereo visits, preserving 13 original exclusions. Both routes ran **16 full and 86 short native lane calls**, with the same 35 CFO updates and ten tail-support fallbacks on 45 short positives. The guarded fractional verifier used the original exact fallback once per aperture. The tail took two exact fallbacks and zero signed-band retries. Both arms opened the actual asynchronous member context. The bounded scope has no following member, so it submitted zero read-ahead requests. Each run was a fresh process under the shared low-priority, one-thread CPU2 lock. All four charged zero process input blocks. [Staged runner and handoff](anchored_cfo_stage.py) · [Guard and resource counters](measurements/anchored-cfo-stage.json.gz)

| Order | CLI | Paid native detector CPU | Fixed-epoch tail CPU | Complete acquisition CPU / wall | Entry to verified seal wall | Worker exit wall |
|---|---|---:|---:|---:|---:|---:|
| Exact then guarded | Exact | 145.90 ms | 35.55 ms | 451.21 / 451.44 ms | 713.41 ms | 818.63 ms |
| Exact then guarded | Guarded | 134.75 ms | 19.62 ms | 346.57 / 347.60 ms | 617.10 ms | 716.54 ms |
| Guarded then exact | Guarded | 135.25 ms | 19.65 ms | 362.93 / 363.23 ms | 654.89 ms | 766.52 ms |
| Guarded then exact | Exact | 146.51 ms | 36.39 ms | 432.29 / 434.18 ms | 710.18 ms | 817.34 ms |

The directly timed detector plus refinement CPU saved **27.08 and 28.00 ms**. The wider acquisition gains of **104.64 and 69.36 ms CPU** leave **77.57 and 41.36 ms** outside those measured stages. Those residuals remain unattributed. The existing exact CLI uses its original full lane load, so the tail difference includes guarded rotation and the exact gather improvement. This trial does not price the guarded tail separately against exact gather. The earlier isolated test provides that comparison. The clocks cover a staged prefix with startup and seal, independent of full acquisition, cold storage and position accuracy. [Paired output and clocks](measurements/anchored-cfo-stage.json.gz) · [Isolated exact-gather comparison](anchored-phase.md)

## Local pack and reproduction

The assembled pack is `/dev/shm/leo-anchored-cfo-raw-pack01`. Its manifest SHA-256 is `0d590b0c7e4ffc468fb17804146362b8534d33d115d83055ae7bbc1dafd967a9`. Twenty-one component and adjacent tests passed, and the opt-in script reaches the original `--named-survivor-finish` and `--exact-graph-reuse` CLI options. The compressed scope receipt SHA-256 is `f1be468038d2a69ad152fed7a465cf3acba6923a8b111e79eb46d7cfe3cf631f`. The scope runner exposes its same staged boundary to an injected test entry, allowing a third receiver to run without repeating either completed control. [Tests](../../../tests/pipeline_eval/test_anchored_cfo_raw.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
entry=reports/ALGO08/v3/anchored_cfo_raw.py
pack=/dev/shm/leo-anchored-cfo-raw-pack01
# Existing donor libraries are optional explicit assembly inputs.
"$install_root/venv/bin/python" -IB "$entry" --assemble-pack /dev/shm/leo-anchored-cfo-new-pack
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -IB "$entry" --anchored-cfo-pack "$pack" --help
gauss "$install_root/venv/bin/python" -IB reports/ALGO08/v3/anchored_cfo_stage.py \
  run "$pack" /dev/shm/leo-anchored-cfo-stage-rebuild
```
