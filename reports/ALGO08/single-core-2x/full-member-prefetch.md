# Reading one full compressed member ahead of ALGO08v3

On one private generated XFS fixture, reading one full member ahead saved **299 ms and 149 ms** in the two cold, reversed-order pairs against ALGO08v3's existing 16 MiB advice. The median incremental saving was **224 ms**. Warm savings were **7 ms and 13 ms**. Process CPU stayed within 27 ms of the control in every pair. All eight timed acquisitions and the seal-verifying preload reproduced the same full detection document, raw authority, ordered probes, and **282 selections**. [Timing and integrity rows](measurements/full-member-prefetch.jsonl)

| Page cache at launch | Arm order | v3 advice wall (s) | Full read wall (s) | v3 advice CPU (s) | Full read CPU (s) |
| --- | --- | ---: | ---: | ---: | ---: |
| Empty | Advice first | 1.9456 | 1.6465 | 1.5513 | 1.5601 |
| Empty | Full read first | 2.0316 | 1.8827 | 1.5802 | 1.5540 |
| Resident | Advice first | 1.6004 | 1.5937 | 1.5565 | 1.5654 |
| Resident | Full read first | 1.6060 | 1.5925 | 1.5705 | 1.5671 |

The three generated members contained 192 dual-antenna windows and **235,675,945 compressed bytes** in total. Each cold arm charged **460,320 filesystem input blocks**, corresponding to **235,683,840 page-rounded bytes**. Each warm arm charged zero. Every prefetched arm consumed both following members, totaling **157,117,910 bytes**, with no fallback. The caller spent 12–14 µs in total collecting the two completed futures. Linux cache checks observed either zero or all 57,540 member pages before each arm. Lower storage-tier residency was unobserved. The eight timed acquisitions used **13.90 s** in aggregate. [Timing and integrity rows](measurements/full-member-prefetch.jsonl)

The variant starts a single read on the first visible window of the preceding member. The I/O worker shares the caller's one-CPU affinity and adds one in-flight compressed buffer, capped at **128 MiB** and about **75 MiB** for this fixture. Peak RSS was unmeasured. The verified path observes the demand-time file identity and checks the compressed member's SHA-256 before decode. It retains index, every window and full decoded member verification, both receiver scans, and their chronological continuation. A stale or failed read falls through to the normal reader. The first member of each segment remains a demand read. Forty-three focused tests covered the ingress, bounded scope, file replacement, corruption and failure ordering, and frozen adapter identity. [Prefetch implementation](../../../tools/pipeline_eval/variants/experimental/receiver_member_prefetch.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_member_lookahead.py)

These measurements stop at acquisition on one generated fixture. The 224 ms is additional to the v3 advice arm on these same data. A previous fixture measured advice against the ordinary reader using a different receiver. The two savings describe independent controls. On saved DS30-0374, v3 took 84.85 s elapsed and 64.40 s CPU from raw input through publication. Hiding its entire 20.46 s of elapsed time outside CPU would still leave 21.97 CPU seconds above the 42.43 s half-time target. A physical, matched-cache comparison through publication would be needed to measure this variant's actual contribution. [Earlier generated-fixture comparison](full-member-lookahead.md) · [Saved physical publication](exact-curved-physical-triage.md)

## Exact invocation and pins

The experiment ran research code at `1929605ce12989bfe43d1170c0d5a5f57dae701f` against the frozen v3 `6cdbac1e8496…` specification. Before timing, the runner authenticated the v3 specification file, receiver, SHA-NI library, compressed-buffer adapter, advice adapter and paired-hash adapter. It used installed runtime `bdb869682a2ea63af4b198a920b763a4c6a78c4c`. The receipt file SHA-256 is `91a7365d4c7218a90ec903794808e345912b2bcd4972e7ae39f226086239274a`. The resume runner SHA-256 is `774d1f5344f5a5682b38160cdd0c5fce07557bee9547b490ad15296c9d430860`. The passive `cachestat` helper SHA-256 is `4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab`. [Receipt](measurements/full-member-prefetch.jsonl) · [Recorded runner](measurements/full-member-prefetch-resume.py)

The fixture sealed near the end of a first invocation capped at 65 s during XFS setup, before that invocation reached any acquisition. The recorded run reused those private generated files. It checked the manifest SHA-256 `a749a509873f7d2bf8d97930f078d39853a4d89cf13e2024a58edf2f94e20f5f`, generation metadata and member identities at launch, and verified every seal during the preload. Cache advice touched only those three inode-matched compressed members. The runner remains tied to that private fixture. [Recorded runner](measurements/full-member-prefetch-resume.py)

```sh
bench=/tmp/leo-algo08v2-2x-bench
repo=/var/tmp/leo-algo08v3-prefetch
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
trial="$repo/reports/ALGO08/single-core-2x"
result_jsonl=/var/tmp/leo-algo08v3-prefetch-replay.jsonl

flock -w 420 "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  timeout --signal=INT 68s env PYTHONPATH="$repo:$release/src:$release" \
  PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$trial/measurements/full-member-prefetch-resume.py" \
  > "$result_jsonl"
```

For regenerating equivalent inputs, the [full fixture runner](full_member_lookahead_trial.py) accepts the certified reference manifest from [the earlier geometry-controlled fixture](full-member-lookahead.md) and `--prefetch` with the exact v3 `integration-exact-curved-lookahead` bundle and its specification file SHA-256 `652f8573e2fdec746dd318849c82992eb7786f014e8dbc393c0352b54e421e46`. The full runner makes three cold pairs and two warm pairs and cleans its private inputs after completion.
