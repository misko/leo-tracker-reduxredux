# Reading and verifying compressed I/Q in 256 KiB blocks

On a 79.6 MB compressed DS30-0374 member, hashing as each block arrived reduced the complete verified reader's median paired CPU by **1.26%**. On an 83.8 MB public southern simulated member it saved **1.15%**. Reader elapsed increased **1.08%** on the physical member and fell **0.77%** on the southern member. Each comparison used four alternating-order pairs after one untimed warmup. [All clocks and verified window digests](measurements/compressed-digest-tiled.json)

| One 64-window chunk | Member read and hash, CPU ms | Full reader, CPU ms |
|---|---:|---:|
| DS30-0374 | 33.20 → 31.39 | 130.80 → 129.07 |
| Southern public simulation | 34.87 → 33.75 | 134.18 → 132.54 |

The measured control reads into one owned buffer and then hashes the compressed member. The experiment fills the same buffer in smaller reads, hashing each completed block while it is still hot. It retains the length and SHA-256 checks before exposing data to the decoder, the bounded regular-file checks, index verification, the paired window/chunk digests, and the check for trailing payload. Each full-reader call returned the first 40 windows of 64 and verified the entire 102.4 MB decoded chunk. Each build returned the same window evidence. Short-read and corruption regressions cover the modified path. Neither build in the physical publication used this experiment. [Verification code](../../../tools/pipeline_eval/variants/experimental/compressed_member_digest.py) · [Regression tests](../../../tests/pipeline_eval/test_experimental_receiver_ingress.py)

Reproduce with the [trial driver](compressed_digest_trial.py), the frozen candidate's `paired-sha256.so`, and one or more `--manifest PATH SHA256` pairs from the measurement receipt. Use the existing one-core benchmark lock. The measurements cover warm file verification and decoding. They do not establish a cold-storage or end-to-end gain.
