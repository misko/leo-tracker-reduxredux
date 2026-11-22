# Acquisition after the faster native receiver

On two sealed Gauss prefixes the frozen receiver sped up the complete acquisition call by **1.37–1.47×**. The verified I/Q reader then consumed **41–50%** of acquisition CPU. Reading the compressed input member directly into one bounded allocation lowered verified-reader CPU by **25–26%** and complete acquisition CPU by **11.6–13.2%** with the frozen receiver in both arms. Both comparisons reproduced the raw authority and the ordered post-continuation probes. [Receipts](receiver-ingress-results.json)

Each timed prefix contained the first 40 scheduled visits of an existing ALGO08 DS30 recording. The normal acquisition caller admitted 36 lower-edge visits and 29 upper-edge visits. The reader checked the entire sealed 64-window compressed member that supplied the prefix. The detector did no work beyond the 40-visit boundary. Both experiments reversed arm order for the upper-edge recording. This measures bounded ingress and detection with the inputs available on the host. It does not include solver time, PNG output, or storage conditions across a full recording.

| Cost | DS30-0016 lower · v2 → final | DS30-0374 upper · v2 → final |
| --- | ---: | ---: |
| Complete `acquire` CPU (s) | 0.710 → 0.483 | 0.579 → 0.422 |
| Native factor calls CPU (s) | 0.496 → 0.272 | 0.367 → 0.203 |
| Verified I/Q reader CPU (s) | 0.201 → 0.200 | 0.202 → 0.210 |
| Python receiver adapter above native calls (ms) | 5.15 → 4.52 | 3.83 → 3.30 |
| Receiver opening, including asset read (ms) | 2.11 → 2.15 | 1.48 → 1.22 |

The existing reader spent about 75–77 ms per chunk in Zstandard stream reads, 57–58 ms in the compressed, decoded-chunk and raw-window hash computations, and 26–39 ms in operating-system reads. The storage clock also covers buffer allocation and the join of bounded read pieces. The native receiver's input conversion and FIR are included in the native clock and separated in the [receiver profile](receiver.md). Writing the partial detection document to an isolated directory, reading it back and rechecking its digest took at most 3.7 ms. Short-prefix serialization costs do not bound that work for a full recording.

## Moving compressed bytes into the decoder

The prototype preallocates one array using the observed file size within the declared compressed member bound and fills it using `readv`. It preserves the regular-file, link-count, maximum-size, and before/after identity checks. It hands a read-only view to the current reader, which still checks the compressed member hash, decoded chunk hash and each window hash. The isolated caller can opt in with `compressed_input_buffer()` for the acquisition call. The input size bound comes from the released reader.

| Input strategy with final detector | DS30-0016 reader CPU (s) | DS30-0016 acquisition CPU (s) | DS30-0374 reader CPU (s) | DS30-0374 acquisition CPU (s) |
| --- | ---: | ---: | ---: | ---: |
| Release, paired with compressed-only | 0.197 | 0.466 | 0.199 | 0.401 |
| Compressed member in one allocation | **0.148** | **0.412** | **0.147** | **0.348** |
| Release, paired with full decoded-chunk buffering | 0.198 | 0.477 | 0.202 | 0.418 |
| Compressed member and full decoded chunk buffered | 0.184 | 0.459 | 0.186 | 0.395 |

Full decoded buffering preserved the same digests but saved less CPU, and the process high-water mark rose to roughly 432,000 KiB from roughly 393,000 KiB before the buffered arm ran. The compressed-only variant kept the existing per-window decode and avoided that larger allocation. The process wrote no sealed input data and its RSS counter covers both arms of a pair.

For an end-to-end candidate, keep the compressed-only approach and use the same immutable source and output checks at the verified-reader boundary. The measured saving is approximately 50 ms per decoded chunk of these prefixes. It is a component result. Reading and hashing improvements alone cannot supply a 2× cold-pipeline gain. Integrity verification remains required for a first analysis of each sealed input. Receiver construction and Python factor normalization are small enough here that rewriting them offers little additional CPU saving.

## Reproduce

Use the frozen `receiver-final-candidate.so` from [the receiver study](receiver.md). The caller needs read access to the two named sealed segment manifests and their first payloads. It creates temporary partial evidence and never publishes a recording or a result. Run from the repository root.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_assets=/opt/leo-algo08/current/assets
algo08_bindings=/srv/bulk/leo-dev/ds30-full-20261121/bindings
algo08_receiver="$algo08_work/receiver-final-candidate.so"

algo08_ingress_profile() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 80s \
    sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python \
    -m tools.pipeline_eval.variants.experimental.receiver_acquisition_profile \
    "$1" "$algo08_receiver" "$algo08_bindings/DS30-0016.json" "$algo08_bindings/DS30-0374.json" \
    --bulk /srv/bulk --assets "$algo08_assets" --visits 40 --ingress "$2"
}

algo08_ingress_profile "$algo08_assets/cancellation-factors.so" release
algo08_ingress_profile "$algo08_receiver" compressed
algo08_ingress_profile "$algo08_receiver" decoded
```

The ingress component tests check equality of the compressed member bytes, enforcement of the original bound and hard-link check, equivalence and read-only ownership of decoded slices, and rejection of decoded length mismatches. The sealed-reader test checks consecutive chunks and rejects corrupted compressed data, per-window hashes and decoded chunk hashes independently. Both measured recordings returned exact raw and probe digests for each ingress path. [Tests](../../../tests/pipeline_eval/test_experimental_receiver_ingress.py)
